"""
tests/test_phase3.py
────────────────────
Phase 3 test checklist:
  [1] LLM Routing: mock Tier 1 to return a low confidence score, verify Tier 2 is called.
  [2] Fallback Logic: mock LLM returning malformed JSON, verify it retries, and upon second failure raises DiagnosisFailedError.
  [3] Diagnosis Persistence: verify that the diagnoses table is populated correctly.
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from sqlalchemy import select

from core.config import settings
from core.models.cases import Case
from core.models.diagnoses import Diagnosis
from core.services.diagnosis import diagnose_case, DiagnosisFailedError

class DummyLLMResult:
    def __init__(self, content: str):
        self.content = content
        self.prompt_version = "diagnosis_v1"
        self.prompt_hash = "dummy_hash"


@pytest.fixture
async def sample_case(db_session):
    event_id = f"payment.failed:pay_01_{uuid.uuid4()}"
    case = Case(
        case_type="failed_subscription",
        customer_ref="cust_123",
        amount=Decimal("100.00"),
        raw_failure_reason="CARD_EXPIRED",
        razorpay_event_id=event_id
    )
    db_session.add(case)
    await db_session.commit()
    return case


@pytest.mark.asyncio
async def test_llm_routing_high_confidence(sample_case, db_session):
    """Tier 1 returns high confidence, Tier 2 is skipped."""
    mock_call_llm = AsyncMock(return_value=DummyLLMResult(
        json.dumps({"causes": ["expired_card"], "confidence": 0.95, "recommended_action": "Request new card"})
    ))
    
    with patch("core.services.diagnosis.call_llm", mock_call_llm):
        diagnosis = await diagnose_case(sample_case.id, db_session, escalation_threshold=0.75)
        
    assert mock_call_llm.call_count == 1
    # Check that Tier 1 was called
    mock_call_llm.assert_called_with(
        prompt_version="diagnosis_v1",
        model=settings.groq_tier1_model,
        user_messages=mock_call_llm.call_args[1]["user_messages"],
    )
    
    assert diagnosis.model_tier == "tier1"
    assert "expired_card" in diagnosis.causes
    assert float(diagnosis.confidence) == pytest.approx(0.95)
    
    # Check persistence
    db_diagnoses = (await db_session.scalars(select(Diagnosis).where(Diagnosis.case_id == sample_case.id))).all()
    assert len(db_diagnoses) == 1
    assert db_diagnoses[0].model_tier == "tier1"


@pytest.mark.asyncio
async def test_llm_routing_escalation(sample_case, db_session):
    """Tier 1 returns low confidence, Tier 2 is called."""
    # First call returns 0.5 (low), second call returns 0.9 (high)
    mock_call_llm = AsyncMock(side_effect=[
        DummyLLMResult(json.dumps({"causes": ["unknown"], "confidence": 0.5, "recommended_action": "Wait"})),
        DummyLLMResult(json.dumps({"causes": ["insufficient_funds"], "confidence": 0.9, "recommended_action": "Retry payment"})),
    ])
    
    with patch("core.services.diagnosis.call_llm", mock_call_llm):
        diagnosis = await diagnose_case(sample_case.id, db_session, escalation_threshold=0.75)
        
    assert mock_call_llm.call_count == 2
    
    # Verify calls
    assert mock_call_llm.call_args_list[0][1]["model"] == settings.groq_tier1_model
    assert mock_call_llm.call_args_list[1][1]["model"] == settings.groq_tier2_model
    
    assert diagnosis.model_tier == "tier2"
    assert "insufficient_funds" in diagnosis.causes


@pytest.mark.asyncio
async def test_fallback_logic_retry(sample_case, db_session):
    """Tier 1 returns malformed JSON, retries and succeeds."""
    mock_call_llm = AsyncMock(side_effect=[
        DummyLLMResult("This is not JSON"),
        DummyLLMResult(json.dumps({"causes": ["expired_card"], "confidence": 0.9, "recommended_action": "Action"}))
    ])
    
    with patch("core.services.diagnosis.call_llm", mock_call_llm):
        diagnosis = await diagnose_case(sample_case.id, db_session)
        
    assert mock_call_llm.call_count == 2
    assert mock_call_llm.call_args_list[0][1]["model"] == settings.groq_tier1_model
    assert mock_call_llm.call_args_list[1][1]["model"] == settings.groq_tier1_model
    
    assert "expired_card" in diagnosis.causes


@pytest.mark.asyncio
async def test_fallback_logic_failure(sample_case, db_session):
    """Tier 1 returns malformed JSON twice, raises exception."""
    mock_call_llm = AsyncMock(side_effect=[
        DummyLLMResult("Bad JSON 1"),
        DummyLLMResult("Bad JSON 2"),
    ])
    
    with patch("core.services.diagnosis.call_llm", mock_call_llm):
        with pytest.raises(DiagnosisFailedError):
            await diagnose_case(sample_case.id, db_session)
            
    assert mock_call_llm.call_count == 2

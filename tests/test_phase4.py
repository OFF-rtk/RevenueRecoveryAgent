"""
tests/test_phase4.py
────────────────────
Phase 4 test checklist:
  [1] Mock channel correctly logs every send attempt.
  [2] Intervention record and AuditEvent are saved correctly in the DB.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import patch, AsyncMock

import pytest
from sqlalchemy import select

from core.models.cases import Case
from core.models.diagnoses import Diagnosis
from core.models.interventions import Intervention
from core.models.audit_events import AuditEvent
from core.services.intervention import draft_and_send_intervention
from core.channels.mock import MockChannel

class DummyLLMResult:
    def __init__(self, content: str):
        self.content = content
        self.prompt_version = "message_draft_v1"
        self.prompt_hash = "dummy_hash"



@pytest.mark.asyncio
async def test_draft_and_send_intervention(sample_case_and_diagnosis, db_session):
    case, diagnosis = sample_case_and_diagnosis

    # Override causes to one that doesn't trigger the no-blind-retry stopping rule.
    # (Phase 4 tests the happy-path template send; stopping-rule behaviour is in Phase 6.)
    diagnosis.causes = ["insufficient_funds"]
    await db_session.commit()

    channel = MockChannel()

    intervention = await draft_and_send_intervention(case.id, db_session, channel=channel)

    expected_template = "payment_recovery_notice_v1"
    expected_params = ["INR", "100.00", "919999999999", "your card had insufficient funds"]
    expected_sent_text = f"[{expected_template}] {expected_params}"

    # Assert Intervention was saved
    db_interventions = (await db_session.scalars(select(Intervention).where(Intervention.case_id == case.id))).all()
    assert len(db_interventions) == 1
    assert db_interventions[0].message_sent == expected_sent_text
    assert db_interventions[0].channel == "mock"
    assert db_interventions[0].attempt_number == 1

    # Assert AuditEvent was saved
    db_audit_events = (
        await db_session.scalars(
            select(AuditEvent)
            .where(AuditEvent.case_id == case.id)
            .where(AuditEvent.event_type == "intervention_sent")
        )
    ).all()
    assert len(db_audit_events) == 1
    assert db_audit_events[0].payload["template_name"] == expected_template
    assert db_audit_events[0].payload["parameters"] == expected_params
    assert db_audit_events[0].payload["channel"] == "mock"


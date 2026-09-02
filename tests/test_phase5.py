import json
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from core.models.cases import Case
from core.models.outcomes import Outcome
from core.models.replies import Reply
from core.models.state_transitions import StateTransition
from core.services.reply_classification import analyze_reply
from core.services.state_machine import process_inbound_reply
from core.webhooks.razorpay import process_webhook


@pytest.fixture
def mock_channel():
    from core.channels.mock import MockChannel
    return MockChannel()


@pytest.mark.asyncio
async def test_classify_reply():
    mock_result = {
        "state": "promise_made",
        "confidence": 0.9,
        "follow_up_hours": 24,
        "reasoning": "Customer promised to pay",
        "message": "Thank you, we will wait.",
        "_meta": {}
    }
    
    mock_llm_response = AsyncMock()
    mock_llm_response.content = json.dumps(mock_result)
    mock_llm_response.prompt_version = "analyze_and_respond_v1"
    mock_llm_response.prompt_hash = "mockhash"
    
    with patch("core.services.reply_classification.call_llm", AsyncMock(return_value=mock_llm_response)):
        mock_case = AsyncMock()
        mock_session = AsyncMock()
        res = await analyze_reply(mock_case, "I will pay tomorrow", mock_session)
        assert res["state"] == "promise_made"
        assert res["follow_up_hours"] == 24
        assert res["message"] == "Thank you, we will wait."

@pytest.mark.asyncio
async def test_process_inbound_reply_promise(sample_case_and_diagnosis, db_session, mock_channel):
    case, _ = sample_case_and_diagnosis
    # Ensure case is in open state
    assert case.status == "open"
    
    mock_classification = {
        "state": "promise_made",
        "confidence": 0.9,
        "follow_up_hours": 24,
        "reasoning": "Test",
        "message": "Thank you, we will wait.",
        "_meta": {}
    }
    
    with patch("core.services.state_machine.analyze_reply", AsyncMock(return_value=mock_classification)):
        await process_inbound_reply(
            customer_ref=case.customer_ref,
            raw_text="I will pay tomorrow",
            session=db_session,
            channel=mock_channel
        )
            
    # Check Case status
    await db_session.refresh(case)
    assert case.status == "promise_pending"
    
    # Check Reply
    replies = (await db_session.scalars(select(Reply).where(Reply.case_id == case.id))).all()
    assert len(replies) == 1
    assert replies[0].raw_reply == "I will pay tomorrow"
    assert replies[0].classified_state == "promise_made"
    
    # Check Transition
    transitions = (await db_session.scalars(select(StateTransition).where(StateTransition.case_id == case.id))).all()
    assert len(transitions) == 1
    assert transitions[0].to_state == "promise_pending"
    
    # Check Outcomes (should be none)
    outcomes = (await db_session.scalars(select(Outcome).where(Outcome.case_id == case.id))).all()
    assert len(outcomes) == 0


@pytest.mark.asyncio
async def test_process_inbound_reply_opt_out(sample_case_and_diagnosis, db_session, mock_channel):
    case, _ = sample_case_and_diagnosis
    
    mock_classification = {
        "state": "opt_out",
        "confidence": 0.99,
        "follow_up_hours": None,
        "reasoning": "Stop",
        "message": "Unsubscribed",
        "_meta": {}
    }
    
    with patch("core.services.state_machine.analyze_reply", AsyncMock(return_value=mock_classification)):
        await process_inbound_reply(
            customer_ref=case.customer_ref,
            raw_text="STOP",
            session=db_session,
            channel=mock_channel
        )
            
    await db_session.refresh(case)
    assert case.status == "stopped"
    
    outcomes = (await db_session.scalars(select(Outcome).where(Outcome.case_id == case.id))).all()
    assert len(outcomes) == 1
    assert outcomes[0].final_state == "stopped"
    assert outcomes[0].amount_recovered == Decimal("0.00")


@pytest.mark.asyncio
async def test_razorpay_payment_captured(sample_case_and_diagnosis, db_session):
    case, _ = sample_case_and_diagnosis
    case.status = "promise_pending"
    await db_session.commit()
    
    payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_12345",
                    "customer_id": case.customer_ref,
                    "amount": 10000,
                    "currency": "INR"
                }
            }
        }
    }
    
    with patch("core.webhooks.razorpay.verify_signature", return_value=None):
        with patch("core.config.settings.phone_number_id", "test_id"):
            with patch("core.config.settings.whatsapp_token", "test_token"):
                with patch("core.channels.whatsapp.WhatsAppChannel.send_template", AsyncMock()) as mock_send:
                    res = await process_webhook(
                        raw_body=b"",
                        signature="test",
                        payload=payload,
                        secret="test",
                        session=db_session
                    )
            
    assert res["status"] == "ok"
    assert res["status_updated"] == "recovered"
    
    await db_session.refresh(case)
    assert case.status == "recovered"
    
    outcomes = (await db_session.scalars(select(Outcome).where(Outcome.case_id == case.id))).all()
    assert len(outcomes) == 1
    assert outcomes[0].final_state == "recovered"
    assert outcomes[0].amount_recovered == Decimal("100.00")
    
    # Check that confirmation was sent
    assert mock_send.call_count == 1
    mock_send.assert_called_with(
        to=case.customer_ref,
        template_name="payment_confirmed_v1",
        parameters=[case.currency, str(case.amount), case.customer_ref]
    )

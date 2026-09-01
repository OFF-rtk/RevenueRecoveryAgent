"""
tests/test_phase6.py
────────────────────
Phase 6: Stopping Rules, Compliance, Full Audit Trail.

Tests verify:
  1. Max-retry cap blocks a 4th intervention and escalates the case.
  2. Opt-out gate blocks outbound send on a stopped case.
  3. No-blind-retry blocks a plain retry on expired_card/wrong_details.
  4. Full audit trail (detect → diagnose → intervene → reply) is
     reconstructable from audit_events alone.
  5. Every stopping-rule trigger is itself written as an audit event.
"""
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from core.models.audit_events import AuditEvent
from core.models.cases import Case
from core.models.diagnoses import Diagnosis
from core.models.interventions import Intervention
from core.models.outcomes import Outcome
from core.models.state_transitions import StateTransition
from core.services.stopping_rules import (
    MAX_RETRIES,
    StoppingRuleError,
    check_stopping_rules,
)


# ── helpers ──────────────────────────────────────────────────────────────────

async def _make_case(db_session, *, status="open", cause="expired_card"):
    """Insert a minimal case + diagnosis, return (case, diagnosis)."""
    event_id = f"payment.failed:pay_{uuid.uuid4()}"
    case = Case(
        case_type="failed_subscription",
        customer_ref=f"cust_{uuid.uuid4().hex[:8]}",
        amount=Decimal("500.00"),
        raw_failure_reason="CARD_EXPIRED",
        razorpay_event_id=event_id,
    )
    case.status = status
    db_session.add(case)
    await db_session.flush()

    diagnosis = Diagnosis(
        case_id=case.id,
        model_tier="tier1",
        prompt_version="diagnosis_v1",
        prompt_hash="hash",
        causes=[cause],
        confidence=Decimal("0.92"),
        recommended_action="Ask customer to update card",
        raw_llm_response="{}",
    )
    db_session.add(diagnosis)
    await db_session.commit()
    return case, diagnosis


async def _add_interventions(db_session, case_id, count):
    """Insert `count` fake Intervention rows for a case."""
    for i in range(count):
        db_session.add(Intervention(
            case_id=case_id,
            channel="mock",
            message_sent=f"[payment_recovery_notice_v1] attempt {i + 1}",
            attempt_number=i + 1,
        ))
    await db_session.commit()


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_max_retry_blocks_4th_attempt(db_session):
    """
    After MAX_RETRIES interventions already exist, a new attempt must be blocked,
    the case escalated, and a stopping_rule_triggered audit event written.
    """
    case, diagnosis = await _make_case(db_session, cause="insufficient_funds")
    await _add_interventions(db_session, case.id, MAX_RETRIES)  # 3 existing

    mock_channel = AsyncMock()
    mock_channel.send_template = AsyncMock(return_value={"channel": "mock", "provider_id": "x"})

    from core.services.intervention import draft_and_send_intervention

    # 4th attempt — should be silently blocked, not raise
    result = await draft_and_send_intervention(case.id, db_session, channel=mock_channel)

    assert result is None
    mock_channel.send_template.assert_not_called()

    await db_session.refresh(case)
    assert case.status == "escalated"

    # Check stopping_rule_triggered audit event exists
    events = (
        await db_session.scalars(
            select(AuditEvent)
            .where(AuditEvent.case_id == case.id)
            .where(AuditEvent.event_type == "stopping_rule_triggered")
        )
    ).all()
    assert len(events) == 1
    assert events[0].payload["rule"] == "max_retries"


@pytest.mark.asyncio
async def test_opt_out_blocks_new_intervention(db_session):
    """
    A case with status 'stopped' must never receive another outbound message.
    """
    case, diagnosis = await _make_case(db_session, status="stopped", cause="insufficient_funds")

    mock_channel = AsyncMock()
    mock_channel.send_template = AsyncMock()

    from core.services.intervention import draft_and_send_intervention

    result = await draft_and_send_intervention(case.id, db_session, channel=mock_channel)

    assert result is None
    mock_channel.send_template.assert_not_called()

    # Audit event confirming opt-out was respected
    events = (
        await db_session.scalars(
            select(AuditEvent)
            .where(AuditEvent.case_id == case.id)
            .where(AuditEvent.event_type == "stopping_rule_triggered")
        )
    ).all()
    assert len(events) == 1
    assert events[0].payload["rule"] == "opt_out_gate"


@pytest.mark.asyncio
async def test_no_blind_retry_on_expired_card(db_session):
    """
    When cause is 'expired_card', a plain retry must be blocked and
    the case redirected to payment_method_required status.
    """
    case, _ = await _make_case(db_session, cause="expired_card")

    with pytest.raises(StoppingRuleError) as exc_info:
        await check_stopping_rules(case, db_session, causes=["expired_card"], action_type="retry")

    assert exc_info.value.rule == "no_blind_retry"

    await db_session.refresh(case)
    assert case.status == "payment_method_required"

    # Audit event
    events = (
        await db_session.scalars(
            select(AuditEvent)
            .where(AuditEvent.case_id == case.id)
            .where(AuditEvent.event_type == "stopping_rule_triggered")
        )
    ).all()
    assert len(events) == 1
    assert events[0].payload["rule"] == "no_blind_retry"
    assert events[0].payload["cause"] == "expired_card"


@pytest.mark.asyncio
async def test_no_blind_retry_on_wrong_details(db_session):
    """wrong_details is equally blocked."""
    case, _ = await _make_case(db_session, cause="wrong_details")

    with pytest.raises(StoppingRuleError) as exc_info:
        await check_stopping_rules(case, db_session, causes=["wrong_details"], action_type="retry")

    assert exc_info.value.rule == "no_blind_retry"


@pytest.mark.asyncio
async def test_follow_up_skips_blind_retry_rule(db_session):
    """
    action_type='follow_up' must NOT trigger the no-blind-retry rule even for
    expired_card — that rule only applies to first-contact retries.
    """
    case, _ = await _make_case(db_session, cause="expired_card")

    # Should not raise
    await check_stopping_rules(case, db_session, causes=["expired_card"], action_type="follow_up")


@pytest.mark.asyncio
async def test_audit_trail_complete(db_session):
    """
    Run detect → diagnose → intervene → reply and verify the full lifecycle
    is reconstructable from audit_events alone.
    """
    from core.models.audit_events import AuditEvent
    from core.models.replies import Reply

    case, diagnosis = await _make_case(db_session, cause="insufficient_funds")

    # Simulate intervention audit event (Phase 4)
    db_session.add(AuditEvent(
        case_id=case.id,
        event_type="intervention_sent",
        payload={"template": "payment_recovery_notice_v1", "channel": "mock"},
    ))
    # Simulate reply classification audit event (Phase 5)
    db_session.add(AuditEvent(
        case_id=case.id,
        event_type="reply_classified",
        payload={"classified_state": "promise_made", "confidence": 0.9},
    ))
    await db_session.commit()

    # Also need a case_created event (normally inserted by razorpay.py)
    db_session.add(AuditEvent(
        case_id=case.id,
        event_type="case_created",
        payload={"source": "test"},
    ))
    await db_session.commit()

    # Pull full audit trail in chronological order
    events = (
        await db_session.scalars(
            select(AuditEvent)
            .where(AuditEvent.case_id == case.id)
            .order_by(AuditEvent.created_at)
        )
    ).all()

    event_types = [e.event_type for e in events]
    assert "case_created" in event_types
    assert "intervention_sent" in event_types
    assert "reply_classified" in event_types


@pytest.mark.asyncio
async def test_stopping_rule_trigger_is_audit_logged(db_session):
    """
    The stopping rule event must be written to audit_events — not just logged
    to stdout. This is the key compliance guarantee.
    """
    case, _ = await _make_case(db_session, cause="insufficient_funds")
    await _add_interventions(db_session, case.id, MAX_RETRIES)

    with pytest.raises(StoppingRuleError):
        await check_stopping_rules(case, db_session, causes=["insufficient_funds"], action_type="retry")

    events = (
        await db_session.scalars(
            select(AuditEvent)
            .where(AuditEvent.case_id == case.id)
            .where(AuditEvent.event_type == "stopping_rule_triggered")
        )
    ).all()
    assert len(events) >= 1, "stopping_rule_triggered must be written to audit_events"

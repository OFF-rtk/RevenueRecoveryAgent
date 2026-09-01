"""
core/services/stopping_rules.py
────────────────────────────────
The "conscience" layer for the Recovery Agent.

Every rule that prevents over-contact, honours opt-outs, and blocks blind
retries on causes that require updated customer info lives here.

Call `check_stopping_rules(case, session)` before any outbound send.
It either returns (allowing the send to proceed) or raises StoppingRuleError,
which the caller must handle by logging and returning early — never crashing.

Rules (evaluated in priority order):
  1. Opt-out gate       — case.status == "stopped" → block immediately
  2. Max-retry cap      — interventions count >= MAX_RETRIES → escalate
  3. No-blind-retry     — cause is expired_card/wrong_details and
                          the attempted action is a plain retry → redirect
                          to payment_method_required flow instead
"""
from __future__ import annotations

import uuid
from typing import Literal

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.audit_events import AuditEvent
from core.models.cases import Case
from core.models.interventions import Intervention
from core.models.outcomes import Outcome
from core.models.state_transitions import StateTransition

log = structlog.get_logger(__name__)

MAX_RETRIES = 3

# Causes that require updated payment info before any retry can happen.
REQUIRES_UPDATED_INFO = {"expired_card", "wrong_details", "invalid_account"}


class StoppingRuleError(Exception):
    """
    Raised when a stopping rule blocks an outbound action.
    Callers should catch this, log it, and return early — never propagate to HTTP layer.
    """
    def __init__(self, rule: str, message: str):
        self.rule = rule
        super().__init__(message)


async def _log_stopping_event(
    session: AsyncSession,
    case_id: uuid.UUID,
    rule: str,
    detail: dict,
) -> None:
    """Append a stopping_rule_triggered audit event. Always committed separately."""
    audit = AuditEvent(
        case_id=case_id,
        event_type="stopping_rule_triggered",
        payload={"rule": rule, **detail},
    )
    session.add(audit)
    await session.commit()
    log.info("stopping_rule_triggered", case_id=str(case_id), rule=rule, **detail)


async def check_opt_out(case: Case, session: AsyncSession) -> None:
    """
    Rule 1: Opt-out gate.
    If the case is already stopped, no further outbound contact is allowed.
    """
    if case.status == "stopped":
        await _log_stopping_event(
            session, case.id, "opt_out_gate",
            {"status": case.status, "reason": "customer_opted_out"},
        )
        raise StoppingRuleError(
            rule="opt_out_gate",
            message=f"Case {case.id} is stopped — outbound contact blocked.",
        )


async def check_max_retries(case: Case, session: AsyncSession) -> None:
    """
    Rule 2: Max-retry cap (hard cap = MAX_RETRIES).
    Counts existing Intervention rows. If already at or above the cap,
    escalates the case and raises StoppingRuleError.
    """
    count = await session.scalar(
        select(func.count()).where(Intervention.case_id == case.id)
    )
    if count is None:
        count = 0

    if count >= MAX_RETRIES:
        old_status = case.status
        case.status = "escalated"

        transition = StateTransition(
            case_id=case.id,
            from_state=old_status,
            to_state="escalated",
            reason="max_retries_reached",
        )
        session.add(transition)

        outcome = Outcome(
            case_id=case.id,
            final_state="escalated",
            amount_recovered=0,
        )
        session.add(outcome)

        await _log_stopping_event(
            session, case.id, "max_retries",
            {"attempt_count": count, "cap": MAX_RETRIES},
        )
        raise StoppingRuleError(
            rule="max_retries",
            message=f"Case {case.id} has reached max retries ({MAX_RETRIES}) — escalated.",
        )


async def check_no_blind_retry(
    case: Case,
    session: AsyncSession,
    causes: list[str] | None,
    action_type: Literal["retry", "follow_up"] = "retry",
) -> None:
    """
    Rule 3: No blind retry on causes requiring updated payment info.
    If cause is in REQUIRES_UPDATED_INFO and a plain retry is attempted,
    redirect by raising StoppingRuleError — the caller should ensure the
    case stays in payment_method_required status instead.
    """
    if action_type != "retry":
        return  # Only applies to retry actions, not follow-up messages

    if not causes:
        return

    for cause in causes:
        if cause.lower() in REQUIRES_UPDATED_INFO:
            # Ensure the case reflects the correct status
            if case.status not in ("payment_method_required", "escalated", "stopped", "recovered"):
                old_status = case.status
                case.status = "payment_method_required"
                transition = StateTransition(
                    case_id=case.id,
                    from_state=old_status,
                    to_state="payment_method_required",
                    reason=f"no_blind_retry:{cause}",
                )
                session.add(transition)

            await _log_stopping_event(
                session, case.id, "no_blind_retry",
                {"cause": cause, "action_blocked": "backend_retry"},
            )
            # We no longer raise an error here for outreach, because we MUST send
            # the WhatsApp template asking the customer to update their card!
            # The status change above is enough to stop automated backend retries.
            return


async def check_dispute_raised(
    case: Case,
    session: AsyncSession,
    causes: list[str] | None,
) -> None:
    """
    Rule 4: Immediate block for disputes.
    If cause is dispute_raised, transition to disputed immediately.
    """
    if not causes:
        return
        
    for cause in causes:
        if cause.lower() == "dispute_raised":
            if case.status not in ("disputed", "escalated", "stopped", "recovered"):
                old_status = case.status
                case.status = "disputed"
                
                transition = StateTransition(
                    case_id=case.id,
                    from_state=old_status,
                    to_state="disputed",
                    reason="cause_is_dispute_raised",
                )
                session.add(transition)
                
                outcome = Outcome(
                    case_id=case.id,
                    final_state="disputed",
                    amount_recovered=0,
                )
                session.add(outcome)

            await _log_stopping_event(
                session, case.id, "dispute_raised",
                {"cause": cause},
            )
            raise StoppingRuleError(
                rule="dispute_raised",
                message=f"Cause '{cause}' means dispute is already active — automated contact blocked.",
            )


async def check_stopping_rules(
    case: Case,
    session: AsyncSession,
    causes: list[str] | None = None,
    action_type: Literal["retry", "follow_up"] = "retry",
) -> None:
    """
    Entrypoint: run all stopping rules in priority order.
    Raises StoppingRuleError if any rule fires — callers must catch this.

    Args:
        case: The Case ORM object (will be mutated if escalation occurs).
        session: Active async DB session.
        causes: The list of diagnosis causes (needed for no-blind-retry rule).
        action_type: "retry" for first-contact/intervention, "follow_up" for
                     state-machine follow-ups (skips no-blind-retry check).
    """
    await check_opt_out(case, session)
    await check_max_retries(case, session)
    await check_no_blind_retry(case, session, causes, action_type)
    await check_dispute_raised(case, session, causes)

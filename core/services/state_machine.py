"""
core/services/state_machine.py
──────────────────────────────
Promise-to-Pay State Machine & Follow-up Drafting.
"""
from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any

import structlog
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from core.channels.base import BaseChannel
from core.config import settings
from core.llm.client import call_llm
from core.models.cases import Case
from core.models.outcomes import Outcome
from core.models.replies import Reply
from core.models.state_transitions import StateTransition
from core.services.reply_classification import classify_reply
from core.services.stopping_rules import StoppingRuleError, check_stopping_rules

log = structlog.get_logger(__name__)


async def draft_and_send_followup(
    case: Case,
    customer_reply: str,
    classified_state: str,
    channel: BaseChannel,
    session: AsyncSession,
) -> None:
    """
    Draft a tone-matched free-text follow-up using gpt-oss-20b
    and send it via the channel.
    """
    prompt_version = "followup_draft_v1"
    
    context = json.dumps({
        "case_type": case.case_type,
        "amount": str(case.amount),
        "currency": case.currency,
        "customer_reply": customer_reply,
        "classified_state": classified_state,
        "payment_link": f"https://rzp.io/i/{case.id.hex[:8]}"
    }, indent=2)
    
    try:
        llm_result = await call_llm(
            prompt_version=prompt_version,
            model=settings.groq_tier1_model,
            user_messages=[{"role": "user", "content": context}],
            response_format={"type": "json_object"},
        )
        parsed = json.loads(llm_result.content)
        message_to_send = parsed["message"]
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        log.error("followup_draft_error", error=str(exc))
        # Fallback message
        message_to_send = "Thank you for your response. We will update your case."

        
    channel_response = await channel.send(
        to=case.customer_ref,
        message=message_to_send
    )
    log.info("followup_sent", case_id=str(case.id), channel=channel.name)

    from core.models.interventions import Intervention
    from core.models.audit_events import AuditEvent

    # Save Intervention record so harness can see it
    intervention = Intervention(
        case_id=case.id,
        channel=channel_response.get("channel", "unknown") if isinstance(channel_response, dict) else "unknown",
        message_sent=message_to_send,
        attempt_number=2
    )
    session.add(intervention)
    
    audit_event = AuditEvent(
        case_id=case.id,
        event_type="followup_sent",
        payload={
            "channel": channel.name,
            "message": message_to_send,
        }
    )
    session.add(audit_event)
    await session.commit()


async def process_inbound_reply(
    customer_ref: str,
    raw_text: str,
    session: AsyncSession,
    channel: BaseChannel,
) -> None:
    """
    Handle an inbound message from a customer.
    Dual-Trigger: If the case is already recovered, just log and ignore.
    Otherwise, classify the reply, transition state, and potentially follow up.
    """
    # 1. Find the active Case for this customer (latest open or pending case)
    # We order by created_at desc to get the most recent case
    case = await session.scalar(
        select(Case)
        .where(Case.customer_ref == customer_ref)
        .order_by(desc(Case.created_at))
        .limit(1)
    )
    
    if not case:
        log.warning("inbound_reply_no_case", customer_ref=customer_ref)
        return
        
    log.info("inbound_reply_matched", case_id=str(case.id), status=case.status)
    
    # 2. Save raw reply first
    reply = Reply(
        case_id=case.id,
        raw_reply=raw_text
    )
    session.add(reply)
    await session.flush()
    
    # 3. Dual-Trigger Outcome Precedence: If already recovered, do not act
    if case.status in ("recovered", "stopped", "escalated", "disputed"):
        log.info(
            "inbound_reply_ignored_terminal_case", 
            case_id=str(case.id), 
            status=case.status
        )
        await session.commit()
        return
        
    # 4. Classify the reply
    classification = await classify_reply(raw_text)
    state = classification["state"]
    
    from sqlalchemy import func
    reply.classified_state = state
    reply.classified_at = func.now()
    
    # 5. Deterministic State Machine Transition
    old_status = case.status
    new_status = old_status
    
    if state == "promise_made":
        new_status = "promise_pending"
        # We simulate follow_up scheduling by just logging it for now, or updating case if we add a column
        follow_up_hours = classification.get("follow_up_hours")
        if follow_up_hours:
            log.info("scheduled_follow_up", case_id=str(case.id), hours=follow_up_hours)
            
    elif state == "needs_new_payment_method":
        new_status = "payment_method_required"
        
    elif state == "disputed":
        new_status = "disputed"
        
    elif state == "opt_out":
        new_status = "stopped"
        
    elif state == "unresolved":
        new_status = old_status # no change to case status
    
    # Apply transition if changed
    if new_status != old_status:
        case.status = new_status
        transition = StateTransition(
            case_id=case.id,
            from_state=old_status,
            to_state=new_status,
            reason=f"customer_reply:{state}"
        )
        session.add(transition)
        
        # If terminal, create Outcome
        if new_status in ("escalated", "stopped", "disputed"):
            outcome = Outcome(
                case_id=case.id,
                final_state=new_status,
                amount_recovered=0.00
            )
            session.add(outcome)
            
    await session.commit()
    
    # 6. Draft and send follow-up if session is open and not terminal
    if new_status not in ("escalated", "stopped", "recovered", "disputed"):
        try:
            await check_stopping_rules(case, session, causes=None, action_type="follow_up")
            await draft_and_send_followup(case, raw_text, state, channel, session)
        except StoppingRuleError as e:
            log.warning(
                "followup_blocked_by_stopping_rule",
                case_id=str(case.id),
                rule=e.rule,
                reason=str(e),
            )

"""
core/services/intervention.py
────────────────────────────
Implements the Intervention Layer (Phase 4).
Drafts a recovery message using the LLM and sends it via a configured channel.
"""
import uuid
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.cases import Case
from core.models.diagnoses import Diagnosis
from core.models.interventions import Intervention
from core.models.audit_events import AuditEvent
from core.channels.base import BaseChannel
from core.channels.mock import MockChannel
from core.services.stopping_rules import StoppingRuleError, check_stopping_rules

log = structlog.get_logger(__name__)

# Default channel for development
default_channel = MockChannel()

async def draft_and_send_intervention(
    case_id: uuid.UUID,
    session: AsyncSession,
    channel: BaseChannel = default_channel
) -> Intervention:
    """
    Looks up the case and its latest diagnosis, selects a pre-approved
    WhatsApp template based on the case type, binds parameters, sends it
    via the channel, and records it.
    """
    case = await session.scalar(select(Case).where(Case.id == case_id))
    if not case:
        raise ValueError(f"Case {case_id} not found")

    # Get latest diagnosis for this case
    diagnosis = await session.scalar(
        select(Diagnosis)
        .where(Diagnosis.case_id == case_id)
        .order_by(Diagnosis.created_at.desc())
        .limit(1)
    )
    
    if not diagnosis:
        raise ValueError(f"No diagnosis found for Case {case_id}")

    if case.case_type == "failed_subscription":
        template_name = "payment_recovery_notice_v1"
    else:
        template_name = "invoice_reminder_notice_v1"

    # Template params: 1: Currency, 2: Amount, 3: Customer Ref, 4: Cause
    parameters = [
        str(case.currency),
        str(case.amount),
        str(case.customer_ref),
        str(diagnosis.causes[0] if diagnosis.causes else "unknown")
    ]
    
    button_parameters = [case.id.hex[:8]]

    # Phase 6: Enforce stopping rules before any outbound send
    try:
        await check_stopping_rules(case, session, causes=diagnosis.causes, action_type="retry")
    except StoppingRuleError as e:
        log.warning(
            "intervention_blocked_by_stopping_rule",
            case_id=str(case_id),
            rule=e.rule,
            reason=str(e),
        )
        return None

    log.info("sending_first_contact_template", case_id=str(case_id), template=template_name)

    # Send via channel (using template)
    channel_response = await channel.send_template(
        to=case.customer_ref, 
        template_name=template_name, 
        parameters=parameters,
        button_parameters=button_parameters
    )
    
    sent_representation = f"[{template_name}] {parameters}"
    
    # Save Intervention record
    intervention = Intervention(
        case_id=case.id,
        channel=channel_response.get("channel", "unknown"),
        message_sent=sent_representation,
        attempt_number=1 # Hardcoded to 1 for now, we will handle multiple attempts in Phase 6
    )
    session.add(intervention)
    
    # Save Audit Event
    audit_event = AuditEvent(
        case_id=case.id,
        event_type="intervention_sent",
        payload={
            "channel": channel_response.get("channel"),
            "template_name": template_name,
            "parameters": parameters,
            "provider_id": channel_response.get("provider_id"),
        }
    )
    session.add(audit_event)
    
    await session.flush()
    return intervention

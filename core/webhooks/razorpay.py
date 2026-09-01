"""
Razorpay webhook processing: signature verification + idempotent case creation.

Two responsibilities kept in one module because they form a single transaction:
  1. verify_signature() — HMAC-SHA256 over raw bytes (stdlib only, no SDK needed)
  2. process_webhook() — idempotency check + case row insert + audit event

Supported event types → case_type mapping:
  payment.failed          → failed_subscription
  subscription.pending    → failed_subscription
  subscription.halted     → failed_subscription
  invoice.expired         → overdue_receivable
  invoice.partially_paid  → overdue_receivable
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.audit_events import AuditEvent
from core.models.cases import Case

log = structlog.get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

SUPPORTED_EVENTS: dict[str, str] = {
    "payment.failed": "failed_subscription",
    "subscription.pending": "failed_subscription",
    "subscription.halted": "failed_subscription",
    "invoice.expired": "overdue_receivable",
    "invoice.partially_paid": "overdue_receivable",
}

SUCCESS_EVENTS = {"payment.captured", "invoice.paid"}


# ── Exceptions ────────────────────────────────────────────────────────────────

class WebhookSignatureError(ValueError):
    """Raised when the X-Razorpay-Signature header does not match."""


class UnsupportedEventError(ValueError):
    """Raised when the webhook event type is not handled by this agent."""


class MalformedPayloadError(ValueError):
    """Raised when the webhook payload is missing required fields."""


# ── Signature verification ────────────────────────────────────────────────────

def verify_signature(raw_body: bytes, signature: str, secret: str) -> None:
    """
    Verify the Razorpay HMAC-SHA256 webhook signature.

    Razorpay computes: HMAC-SHA256(raw_request_body, webhook_secret)
    and sends the hex digest in the X-Razorpay-Signature header.

    Uses hmac.compare_digest (constant-time) to prevent timing attacks.

    Raises WebhookSignatureError if the signature does not match.
    """
    expected = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        log.error(
            "webhook_signature_mismatch",
            expected_prefix=expected[:8],
            received_prefix=signature[:8] if signature else "<empty>",
        )
        raise WebhookSignatureError("Webhook signature does not match")


# ── Entity ID extraction ──────────────────────────────────────────────────────

def _extract_entity_id(event_type: str, payload: dict[str, Any]) -> str:
    """
    Extract the primary entity ID from a Razorpay webhook payload.

    Razorpay payloads follow the structure:
        payload.{entity_name}.entity.id

    For example, payment.failed → payload.payment.entity.id = "pay_ABC"
    """
    entity_name = event_type.split(".")[0]  # "payment", "subscription", "invoice"
    try:
        entity_id = payload["payload"][entity_name]["entity"]["id"]
    except (KeyError, TypeError) as exc:
        raise MalformedPayloadError(
            f"Cannot extract entity ID for event '{event_type}': {exc}"
        ) from exc
    return str(entity_id)


def _build_idempotency_key(event_type: str, entity_id: str) -> str:
    """Build a deterministic idempotency key: '{event_type}:{entity_id}'."""
    return f"{event_type}:{entity_id}"


# ── Case extraction helpers ───────────────────────────────────────────────────

def _extract_customer_ref(event_type: str, payload: dict[str, Any]) -> str:
    """Extract a customer identifier from the payload (email, contact, or ID)."""
    entity_name = event_type.split(".")[0]
    entity = payload.get("payload", {}).get(entity_name, {}).get("entity", {})
    return (
        entity.get("email")
        or entity.get("contact")
        or entity.get("customer_id")
        or "unknown"
    )


def _extract_amount(event_type: str, payload: dict[str, Any]) -> Decimal:
    """Extract amount in rupees (Razorpay sends paise as integers)."""
    entity_name = event_type.split(".")[0]
    entity = payload.get("payload", {}).get(entity_name, {}).get("entity", {})
    paise = entity.get("amount") or entity.get("amount_due") or 0
    return Decimal(str(paise)) / Decimal("100")


def _extract_failure_reason(event_type: str, payload: dict[str, Any]) -> str | None:
    """Extract the raw failure reason code from the payload, if present."""
    entity_name = event_type.split(".")[0]
    entity = payload.get("payload", {}).get(entity_name, {}).get("entity", {})
    return (
        entity.get("error_code")
        or entity.get("error_description")
        or entity.get("status")
    )


# ── Main processor ────────────────────────────────────────────────────────────

async def process_webhook(
    raw_body: bytes,
    signature: str,
    payload: dict[str, Any],
    secret: str,
    session: AsyncSession,
) -> dict[str, Any]:
    """
    Verify, deduplicate, and persist a Razorpay webhook event as a Case row.

    Returns a dict suitable for the HTTP response body.

    Flow:
      1. Verify HMAC signature — raises WebhookSignatureError on mismatch
      2. Check event type is supported — raises UnsupportedEventError otherwise
      3. Build idempotency key from event_type + entity_id
      4. Check for existing case with that key — return early if duplicate
      5. Insert new Case row + AuditEvent row in one transaction
    """
    # 1. Signature
    verify_signature(raw_body, signature, secret)

    event_type: str = payload.get("event", "")

    # 2. Supported event check
    if event_type not in SUPPORTED_EVENTS and event_type not in SUCCESS_EVENTS:
        log.info("webhook_event_ignored", event_type=event_type)
        return {"status": "ignored", "reason": f"event type '{event_type}' not handled"}

    try:
        entity_id = _extract_entity_id(event_type, payload)
        customer_ref = _extract_customer_ref(event_type, payload)
        
        # 3. Success event handling
        if event_type in SUCCESS_EVENTS:
            log.info("webhook_success_event", event_type=event_type, entity_id=entity_id)
            # Find the active Case for this customer (latest open or pending case)
            from sqlalchemy import desc
            from core.models.outcomes import Outcome
            from core.models.state_transitions import StateTransition
            
            case = await session.scalar(
                select(Case)
                .where(Case.customer_ref == customer_ref)
                .order_by(desc(Case.created_at))
                .limit(1)
            )
            if not case or case.status in ("recovered", "stopped", "escalated"):
                log.info("webhook_success_no_active_case", customer_ref=customer_ref)
                return {"status": "ok", "reason": "no active case to recover"}
                
            old_status = case.status
            case.status = "recovered"
            
            transition = StateTransition(
                case_id=case.id,
                from_state=old_status,
                to_state="recovered",
                reason=f"razorpay_webhook:{event_type}"
            )
            session.add(transition)
            
            outcome = Outcome(
                case_id=case.id,
                final_state="recovered",
                amount_recovered=case.amount
            )
            session.add(outcome)
            await session.commit()
            
            # Send confirmation if we want (Phase 5 requires it if no session open, handled by template)
            from core.channels.whatsapp import WhatsAppChannel
            from core.config import settings
            channel = WhatsAppChannel(settings.phone_number_id, settings.whatsapp_token)
            await channel.send_template(
                to=customer_ref,
                template_name="payment_confirmed_v1",
                parameters=[case.currency, str(case.amount), customer_ref]
            )
            
            return {"status": "ok", "case_id": str(case.id), "status_updated": "recovered"}
            
        # 4. Failure event handling (create case)
        case_type = SUPPORTED_EVENTS[event_type]
        idempotency_key = _build_idempotency_key(event_type, entity_id)

        log.info(
            "webhook_received",
            event_type=event_type,
            entity_id=entity_id,
            idempotency_key=idempotency_key,
            case_type=case_type,
        )

        # 5. Idempotency check
        existing = await session.scalar(
            select(Case.id).where(Case.razorpay_event_id == idempotency_key)
        )
        if existing is not None:
            log.info(
                "webhook_deduplicated",
                idempotency_key=idempotency_key,
                existing_case_id=str(existing),
            )
            return {
                "status": "duplicate",
                "deduplicated": True,
                "existing_case_id": str(existing),
            }

        # 5. Insert case + audit event
        case = Case(
            razorpay_event_id=idempotency_key,
            case_type=case_type,
            status="open",
            customer_ref=_extract_customer_ref(event_type, payload),
            amount=_extract_amount(event_type, payload),
            currency="INR",
            raw_failure_reason=_extract_failure_reason(event_type, payload),
            raw_payload=payload,
        )
    except (KeyError, TypeError, ValueError) as exc:
        if not isinstance(exc, MalformedPayloadError):
            raise MalformedPayloadError(f"Malformed payload: {exc}") from exc
        raise
    session.add(case)
    await session.flush()  # populate case.id before using it in AuditEvent

    audit = AuditEvent(
        case_id=case.id,
        event_type="case_created",
        payload={
            "source": "razorpay_webhook",
            "razorpay_event": event_type,
            "entity_id": entity_id,
        },
    )
    session.add(audit)
    await session.commit()

    log.info(
        "case_created",
        case_id=str(case.id),
        case_type=case_type,
        amount=str(case.amount),
        customer_ref=case.customer_ref,
    )

    return {
        "status": "ok",
        "case_id": str(case.id),
        "case_type": case_type,
    }

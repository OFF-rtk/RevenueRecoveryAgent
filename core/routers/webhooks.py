"""
FastAPI router for Razorpay webhooks.

Critical: we read the raw request body BEFORE any JSON parsing so the HMAC
is computed over the exact bytes Razorpay signed. If we let FastAPI parse the
body first, we lose byte-for-byte fidelity (e.g. key ordering, whitespace).
"""
from __future__ import annotations

import json

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.db import get_session
from core.models.audit_events import AuditEvent
from core.services.pipeline import process_new_webhook_case
from core.webhooks.razorpay import (
    MalformedPayloadError,
    UnsupportedEventError,
    WebhookSignatureError,
    process_webhook,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/razorpay", summary="Receive Razorpay webhook events")
async def razorpay_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Accept and process Razorpay webhook events.

    - Verifies HMAC-SHA256 signature (returns 400 on mismatch)
    - Deduplicates by razorpay_event_id (returns 200 with deduplicated=true)
    - Creates a Case row + AuditEvent on first receipt
    """
    # Read raw bytes — required for HMAC verification over the exact signed body
    raw_body: bytes = await request.body()
    signature: str = request.headers.get("X-Razorpay-Signature", "")

    # Parse JSON from the same raw bytes (don't call request.json() separately)
    try:
        payload: dict = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        log.error("webhook_invalid_json", error=str(exc))
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    try:
        result = await process_webhook(
            raw_body=raw_body,
            signature=signature,
            payload=payload,
            secret=settings.razorpay_webhook_secret,
            session=session,
        )
        
        # If a new case was created, trigger the background pipeline
        if result.get("status") == "ok" and "case_id" in result and not result.get("status_updated"):
            import uuid
            case_id_str = result["case_id"]
            background_tasks.add_task(process_new_webhook_case, uuid.UUID(case_id_str))

    except WebhookSignatureError as exc:
        log.error("webhook_rejected_bad_signature")
        raise HTTPException(status_code=400, detail="Invalid webhook signature") from exc
    except UnsupportedEventError as exc:
        # Already logged in process_webhook; return 200 so Razorpay stops retrying
        return {"status": "ignored"}
    except MalformedPayloadError as exc:
        log.error("webhook_malformed_payload", error=str(exc))
        # Return 200 so Razorpay stops retrying a payload we can never parse
        return {"status": "ignored", "reason": "malformed payload"}
    except Exception as exc:
        log.exception("webhook_processing_error", error=str(exc))
        raise HTTPException(status_code=500, detail="Internal error") from exc

    return result


@router.get("/whatsapp", summary="Meta Webhook Verification")
async def verify_whatsapp_webhook(request: Request) -> Response:
    """
    Handles the Meta Cloud API webhook verification handshake.
    """
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == settings.whatsapp_verify_token:
        log.info("whatsapp_webhook_verified")
        return Response(content=challenge, media_type="text/plain")
    else:
        log.warning("whatsapp_webhook_verification_failed")
        raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/whatsapp", summary="Receive WhatsApp Webhook events")
async def whatsapp_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Receive inbound messages and statuses from WhatsApp Cloud API.
    """
    try:
        payload = await request.json()
    except json.JSONDecodeError as exc:
        log.error("whatsapp_webhook_invalid_json", error=str(exc))
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    log.info("whatsapp_webhook_received", payload=payload)
    
    # Write everything to audit_events unconditionally
    audit_event = AuditEvent(
        event_type="whatsapp_webhook_received",
        payload=payload
    )
    session.add(audit_event)
    
    # Extract inbound messages
    try:
        entry = payload.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        
        if "messages" in value:
            messages = value["messages"]
            for msg in messages:
                sender_number = msg.get("from")
                if msg.get("type") == "text":
                    text_body = msg["text"].get("body", "")
                    log.info(
                        "whatsapp_inbound_message", 
                        sender=sender_number, 
                        text=text_body
                    )
                    # Hand off to reply-classification pipeline (Phase 5)
                    # Use WhatsAppChannel instance
                    from core.services.state_machine import process_inbound_reply
                    
                    if settings.use_mock_channel:
                        from core.channels.mock import MockChannel
                        channel = MockChannel()
                    else:
                        from core.channels.whatsapp import WhatsAppChannel
                        channel = WhatsAppChannel(
                            phone_number_id=settings.phone_number_id,
                            api_token=settings.whatsapp_token
                        )
                    await process_inbound_reply(
                        customer_ref=sender_number,
                        raw_text=text_body,
                        session=session,
                        channel=channel
                    )
        elif "statuses" in value:
            # Ignore delivery/read receipts quietly
            pass
        
    except Exception as exc:
        log.error("whatsapp_payload_extraction_error", error=str(exc))
        # Keep processing and return 200, we already logged to DB
    
    await session.commit()
    return {"status": "success"}

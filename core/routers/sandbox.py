import asyncio
import time
import httpx
import uuid
import hmac
import hashlib
import json
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Header
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
import os

from core.db import get_db, async_session_factory
from core.models.cases import Case
from core.models.diagnoses import Diagnosis
from core.models.audit_events import AuditEvent
from core.models.interventions import Intervention
from core.models.replies import Reply
from core.config import settings

from scripts.run_live_persona_harness import get_persona_reply

from scripts.trigger_followup import check_followup

router = APIRouter(prefix="/api/sandbox", tags=["sandbox"])
cases_router = APIRouter(prefix="/api/cases", tags=["cases"])

# --- Cases Explorer Endpoints (Unchanged) ---
@cases_router.get("")
async def get_cases(status: Optional[str] = None, case_type: Optional[str] = None, session: AsyncSession = Depends(get_db)):
    query = select(Case).where(~Case.customer_ref.startswith('test_')).order_by(desc(Case.created_at)).limit(100)
    if status:
        query = query.where(Case.status == status)
    if case_type:
        query = query.where(Case.case_type == case_type)
        
    result = await session.execute(query)
    cases = result.scalars().all()
    
    return [{"id": str(c.id), "customer_ref": c.customer_ref, "amount": float(c.amount), "status": c.status, "outcome": None, "created_at": c.created_at} for c in cases]

@cases_router.get("/{case_id}/timeline")
async def get_case_timeline(case_id: str, session: AsyncSession = Depends(get_db)):
    audit_events = await session.scalars(
        select(AuditEvent).where(AuditEvent.case_id == case_id).order_by(AuditEvent.created_at)
    )
    
    timeline = []
    for e in audit_events:
        timeline.append({
            "type": "audit" if e.event_type not in ["state_transition", "agent_intervention", "customer_reply", "followup_sent", "intervention_sent", "diagnosis_completed"] else e.event_type,
            "event": e.event_type,
            "payload": e.payload,
            "timestamp": e.created_at
        })
        
    return timeline

@cases_router.get("/{case_id}/chat")
async def get_case_chat(case_id: str, session: AsyncSession = Depends(get_db)):
    interventions = await session.scalars(select(Intervention).where(Intervention.case_id == case_id))
    replies = await session.scalars(select(Reply).where(Reply.case_id == case_id))
    
    chat = []
    for i in interventions:
        chat.append({"role": "agent", "message": i.message_sent, "timestamp": i.sent_at})
    for r in replies:
        chat.append({"role": "customer", "message": r.raw_reply, "timestamp": r.received_at})
        
    chat.sort(key=lambda x: x["timestamp"])
    return chat

@cases_router.get("/{case_id}/audit")
async def get_case_audit(case_id: str, session: AsyncSession = Depends(get_db)):
    audit_events = await session.scalars(select(AuditEvent).where(AuditEvent.case_id == case_id).order_by(AuditEvent.created_at))
    return [{"event": e.event_type, "payload": e.payload, "timestamp": e.created_at} for e in audit_events]

# --- Sandbox API (Isolated In-Memory Polling) ---

# Global State for Sandbox Sessions
# Keys: session_id, Values: {"events": [], "done": bool, "error": bool, "timestamp": float}
SANDBOX_SESSIONS: Dict[str, Dict[str, Any]] = {}
MAX_SESSIONS = 1000

# Rate limiting state
RATE_LIMIT_STORE = {"count": 0, "reset_at": time.time() + 3600}

def verify_sandbox_key(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    
    # Strip "Bearer " if present, though we might just pass the raw key
    key = authorization.replace("Bearer ", "").strip()
    expected_key = os.environ.get("SANDBOX_ACCESS_KEY", "mock-sandbox-key")
    
    if key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid access key")
        
    # Rate limiter check
    now = time.time()
    if now > RATE_LIMIT_STORE["reset_at"]:
        RATE_LIMIT_STORE["count"] = 0
        RATE_LIMIT_STORE["reset_at"] = now + 3600
        
    if RATE_LIMIT_STORE["count"] >= 20: # 20 requests per hour
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")
        
    return key

class SandboxRunRequest(BaseModel):
    persona: str = "considering_cancellation"
    case_type: str = "failed_subscription"
    root_cause: str = "insufficient_funds"

def cleanup_old_sessions():
    """Simple GC to prevent memory leaks in global state."""
    if len(SANDBOX_SESSIONS) > MAX_SESSIONS:
        # Remove oldest 100 sessions
        sorted_sessions = sorted(SANDBOX_SESSIONS.items(), key=lambda x: x[1].get("timestamp", 0))
        for k, _ in sorted_sessions[:100]:
            SANDBOX_SESSIONS.pop(k, None)

PORT = os.environ.get("PORT", "8001")
RAZORPAY_WEBHOOK_URL = f"http://127.0.0.1:{PORT}/webhooks/razorpay"
WHATSAPP_WEBHOOK_URL = f"http://127.0.0.1:{PORT}/webhooks/whatsapp"
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "test_webhook_secret_phase1")
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "test_whatsapp_secret")

def generate_razorpay_signature(payload_bytes: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

def generate_whatsapp_signature(payload_bytes: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

async def send_razorpay_webhook(phone: str, root_cause: str, case_type: str, client: httpx.AsyncClient):
    # case_type drives which Razorpay event we fire -- these map to different
    # case_type values in the app (see core/webhooks/razorpay.py SUPPORTED_EVENTS),
    # which in turn selects a different message template and audit trail.
    if case_type == "overdue_invoice":
        payload_dict = {
            "entity": "event",
            "account_id": "acc_1234567890",
            "event": "invoice.expired",
            "contains": ["invoice"],
            "payload": {
                "invoice": {
                    "entity": {
                        "id": f"inv_{int(time.time())}_{phone[-4:]}",
                        "amount": 499900,
                        "amount_due": 499900,
                        "currency": "INR",
                        "status": "expired",
                        "description": "Overdue Invoice - Business Services",
                        "error_description": f"Invoice payment overdue: {root_cause}",
                        "error_reason": root_cause,
                        "contact": phone,
                        "notes": {"customer_ref": phone}
                    }
                }
            },
            "created_at": int(time.time())
        }
    else:
        payload_dict = {
            "entity": "event",
            "account_id": "acc_1234567890",
            "event": "payment.failed",
            "contains": ["payment"],
            "payload": {
                "payment": {
                    "entity": {
                        "id": f"pay_{int(time.time())}_{phone[-4:]}",
                        "amount": 99900,
                        "currency": "INR",
                        "status": "failed",
                        "method": "card",
                        "description": "Razorpay Premium Annual Subscription",
                        "error_code": "BAD_REQUEST_ERROR",
                        "error_description": f"Payment failed due to {root_cause}",
                        "error_source": "bank",
                        "error_reason": root_cause,
                        "contact": phone,
                        "notes": {"customer_ref": phone}
                    }
                }
            },
            "created_at": int(time.time())
        }
    payload_bytes = json.dumps(payload_dict, separators=(",", ":")).encode("utf-8")
    signature = generate_razorpay_signature(payload_bytes, RAZORPAY_WEBHOOK_SECRET)
    headers = {"Content-Type": "application/json", "X-Razorpay-Signature": signature}
    return await client.post(RAZORPAY_WEBHOOK_URL, content=payload_bytes, headers=headers)

async def send_payment_captured(phone: str, client: httpx.AsyncClient):
    payload_dict = {
        "entity": "event",
        "account_id": "acc_1234567890",
        "event": "payment.captured",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": f"pay_cap_{int(time.time())}_{phone[-4:]}",
                    "amount": 99900,
                    "currency": "INR",
                    "status": "captured",
                    "contact": phone,
                    "notes": {"customer_ref": phone}
                }
            }
        },
        "created_at": int(time.time())
    }
    payload_bytes = json.dumps(payload_dict, separators=(",", ":")).encode("utf-8")
    signature = generate_razorpay_signature(payload_bytes, RAZORPAY_WEBHOOK_SECRET)
    headers = {"Content-Type": "application/json", "X-Razorpay-Signature": signature}
    return await client.post(RAZORPAY_WEBHOOK_URL, content=payload_bytes, headers=headers)

async def send_whatsapp_webhook(phone: str, message: str, client: httpx.AsyncClient):
    payload_dict = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "1234567890",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "15556682442", "phone_number_id": "123"},
                    "contacts": [{"profile": {"name": "Synthetic User"}, "wa_id": phone}],
                    "messages": [{
                        "from": phone,
                        "id": f"wamid.{uuid.uuid4().hex}",
                        "timestamp": str(int(time.time())),
                        "text": {"body": message},
                        "type": "text"
                    }]
                },
                "field": "messages"
            }]
        }]
    }
    payload_bytes = json.dumps(payload_dict, separators=(",", ":")).encode("utf-8")
    signature = generate_whatsapp_signature(payload_bytes, WHATSAPP_APP_SECRET)
    headers = {"Content-Type": "application/json", "X-Hub-Signature-256": signature}
    return await client.post(WHATSAPP_WEBHOOK_URL, content=payload_bytes, headers=headers)

async def run_sandbox_simulation(session_id: str, req: SandboxRunRequest):
    # We will use the database and production webhooks
    customer_ref = f"test_{uuid.uuid4().hex[:8]}"
    
    # Store customer_ref in session state
    SANDBOX_SESSIONS[session_id]["customer_ref"] = customer_ref
    
    try:
        # Trigger webhook
        async with httpx.AsyncClient(timeout=60.0) as client:
            await send_razorpay_webhook(customer_ref, req.root_cause, req.case_type, client)
            
        async_session = async_session_factory()

        seen_interventions = []
        conversation_summary = ""
        replies_sent = 0
        rounds_stalled = 0
        # How many times in a row the case has landed back in promise_pending
        # without paying -- used to force a real reminder (see below).
        promise_streak = 0
        reminder_forced_this_streak = False
        # Set at the end of a round that just sent a reply during a promise
        # streak; consumed at the *start* of the next round (after the normal
        # sleep gives the backend time to actually process that reply) so we
        # never call check_followup against state that hasn't landed yet.
        pending_reminder_force = False

        for round_idx in range(40):
            await asyncio.sleep(2)
            async with async_session() as session:
                case_row = await session.scalar(
                    select(Case).where(Case.customer_ref == customer_ref).order_by(desc(Case.created_at)).limit(1)
                )
                if not case_row:
                    continue

                SANDBOX_SESSIONS[session_id]["case_id"] = str(case_row.id)

                if pending_reminder_force:
                    pending_reminder_force = False
                    # Re-check status rather than trusting the flag blindly --
                    # the backend's own broken-promise rule (3 promise_made
                    # replies -> human_escalated) could have already resolved
                    # this case in the meantime, and forcing a "still waiting
                    # for your payment" reminder onto an already-escalated case
                    # would be a confusing thing to show in a demo.
                    if case_row.status == "promise_pending":
                        # Send the actual payment_reminder_followup_v1 template
                        # (not another reactive LLM reply) so the demo shows the
                        # real proactive reminder firing, not just back-and-forth
                        # acknowledgments. session_window_hours is forced near-
                        # zero: the sandbox can never wait out the real 24h
                        # "session open" window, so without this the template
                        # branch is unreachable once the customer has replied
                        # even once.
                        await check_followup(str(case_row.id), force=True, session_window_hours=0.0001)
                    continue

                intervention = await session.scalar(
                    select(Intervention).where(Intervention.case_id == case_row.id).order_by(desc(Intervention.sent_at)).limit(1)
                )

                has_unseen = intervention and str(intervention.id) not in seen_interventions

                if case_row.status in ("recovered", "retained_paused", "stopped", "human_escalated", "timeout") and not has_unseen:
                    SANDBOX_SESSIONS[session_id]["done"] = True
                    return

                if has_unseen:
                    rounds_stalled = 0
                    seen_interventions.append(str(intervention.id))
                    agent_text = intervention.message_sent

                    if case_row.status == "promise_pending":
                        promise_streak += 1
                    else:
                        promise_streak = 0
                        reminder_forced_this_streak = False

                    # Persona replies
                    llm_resp = await get_persona_reply(
                        persona_type=req.persona,
                        conversation_summary=conversation_summary,
                        latest_agent_message=agent_text,
                        temperature=0.7
                    )

                    conversation_summary = llm_resp.get("conversation_summary", conversation_summary)
                    reply_text = llm_resp.get("reply_text", "").strip()
                    action = llm_resp.get("action", "undecided")

                    async with httpx.AsyncClient(timeout=60.0) as client:
                        if action == "pay_now":
                            await send_payment_captured(customer_ref, client)
                            continue

                        if reply_text:
                            await send_whatsapp_webhook(customer_ref, reply_text, client)
                            replies_sent += 1

                            # Fire after the *first* promise, not the second --
                            # the natural conversation can reach the backend's
                            # own 3-broken-promises cap as early as the very
                            # next round, so waiting any longer risks the
                            # reminder landing after the case has already been
                            # escalated (see the status re-check above).
                            if promise_streak >= 1 and not reminder_forced_this_streak:
                                reminder_forced_this_streak = True
                                pending_reminder_force = True
                else:
                    rounds_stalled += 1
                    if rounds_stalled >= 3:
                        # force a manual follow-up to advance the stale case
                        await check_followup(str(case_row.id), force=True)
                        rounds_stalled = 0

        SANDBOX_SESSIONS[session_id]["done"] = True
    except Exception as e:
        import traceback
        SANDBOX_SESSIONS[session_id]["done"] = True
        SANDBOX_SESSIONS[session_id]["error"] = True
        SANDBOX_SESSIONS[session_id]["error_detail"] = f"{type(e).__name__}: {e}"
        print(f"⚠️ Sandbox simulation error ({session_id}): {type(e).__name__}: {e}")
        traceback.print_exc()


@router.post("/run")
async def start_sandbox_run(req: SandboxRunRequest, background_tasks: BackgroundTasks, _key: str = Depends(verify_sandbox_key)):
    RATE_LIMIT_STORE["count"] += 1
    cleanup_old_sessions()
    
    session_id = str(uuid.uuid4())
    SANDBOX_SESSIONS[session_id] = {
        "events": [],
        "done": False,
        "error": False,
        "timestamp": time.time()
    }
    
    background_tasks.add_task(run_sandbox_simulation, session_id, req)
    
    return {"session_id": session_id}

@router.get("/run/{session_id}/status")
async def get_sandbox_status(session_id: str, session: AsyncSession = Depends(get_db), _key: str = Depends(verify_sandbox_key)):
    session_data = SANDBOX_SESSIONS.get(session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found or expired")
        
    case_id = session_data.get("case_id")
    events = []
    
    if case_id:
        audit_events = await session.scalars(select(AuditEvent).where(AuditEvent.case_id == case_id).order_by(AuditEvent.created_at))
        interventions = await session.scalars(select(Intervention).where(Intervention.case_id == case_id))
        replies = await session.scalars(select(Reply).where(Reply.case_id == case_id))
        
        # We try to reconstruct the events list frontend expects
        for e in audit_events:
            payload = dict(e.payload) if e.payload else {}
            if e.event_type == "state_transition":
                # Ensure the 'new_status' is picked up by frontend properly if 'to_state' is used
                payload["new_status"] = payload.get("to_state", "")

            events.append({
                "type": e.event_type,
                "event": e.event_type,
                "timestamp": e.created_at.timestamp(),
                "payload": payload
            })
            
        events.sort(key=lambda x: x["timestamp"])

    if session_data.get("error") and session_data.get("error_detail"):
        events.append({
            "type": "error",
            "event": "error",
            "timestamp": time.time(),
            "payload": {"message": session_data["error_detail"]}
        })

    return {
        "events": events,
        "done": session_data["done"],
        "error": session_data["error"],
        "error_detail": session_data.get("error_detail")
    }

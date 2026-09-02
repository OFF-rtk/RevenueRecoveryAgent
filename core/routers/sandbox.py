import asyncio
import time
import httpx
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

from core.db import get_db
from core.models.cases import Case
from core.models.diagnoses import Diagnosis
from core.models.audit_events import AuditEvent
from core.models.interventions import Intervention
from core.models.replies import Reply
from core.models.state_transitions import StateTransition
from core.config import settings

from scripts.run_live_persona_harness import send_razorpay_webhook, send_whatsapp_webhook, get_persona_reply
from scripts.trigger_followup import check_followup
from core.services.state_machine import process_inbound_reply
from core.channels.whatsapp import WhatsAppChannel

router = APIRouter(prefix="/api/sandbox", tags=["sandbox"])
cases_router = APIRouter(prefix="/api/cases", tags=["cases"])

# --- Case Explorer Endpoints ---

@cases_router.get("")
async def get_cases(status: Optional[str] = None, case_type: Optional[str] = None, session: AsyncSession = Depends(get_db)):
    query = select(Case).order_by(desc(Case.created_at)).limit(100)
    if status:
        query = query.where(Case.status == status)
    if case_type:
        query = query.where(Case.case_type == case_type)
        
    result = await session.execute(query)
    cases = result.scalars().all()
    
    # Optional: fetch diagnoses for these cases to enrich the response
    return [{"id": str(c.id), "customer_ref": c.customer_ref, "amount": float(c.amount), "status": c.status, "outcome": None, "created_at": c.created_at} for c in cases]

@cases_router.get("/{case_id}/timeline")
async def get_case_timeline(case_id: str, session: AsyncSession = Depends(get_db)):
    """Unified chronological feed for a single case using the Append-Only Audit Ledger."""
    audit_events = await session.scalars(
        select(AuditEvent).where(AuditEvent.case_id == case_id).order_by(AuditEvent.created_at)
    )
    
    timeline = []
    for e in audit_events:
        timeline.append({
            "type": "audit" if e.event_type not in ["state_transition", "agent_intervention", "customer_reply", "followup_sent", "intervention_sent"] else e.event_type,
            "event": e.event_type,
            "payload": e.payload,
            "timestamp": e.created_at
        })
        
    return timeline

@cases_router.get("/{case_id}/chat")
async def get_case_chat(case_id: str, session: AsyncSession = Depends(get_db)):
    """Polls interventions and replies to render the chat bubbles."""
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

# --- Sandbox Interaction Endpoints ---

class TriggerRequest(BaseModel):
    phone: str
    amount: float = 999.00
    persona: str = "considering_cancellation"
    root_cause: str = "insufficient_funds"

@router.post("/trigger")
async def trigger_sandbox_case(req: TriggerRequest, background_tasks: BackgroundTasks):
    async def fire_webhook():
        async with httpx.AsyncClient() as client:
            from scripts.run_live_persona_harness import generate_razorpay_signature, RAZORPAY_WEBHOOK_SECRET, RAZORPAY_WEBHOOK_URL
            import time
            import json
            
            payload_dict = {
                "entity": "event",
                "account_id": "acc_1234567890",
                "event": "payment.failed",
                "contains": ["payment"],
                "payload": {
                    "payment": {
                        "entity": {
                            "id": f"pay_{int(time.time())}_{req.phone[-4:]}",
                            "amount": int(req.amount * 100),
                            "currency": "INR",
                            "status": "failed",
                            "method": "card",
                            "description": "Razorpay Premium Annual Subscription",
                            "error_code": "BAD_REQUEST_ERROR",
                            "error_description": f"Payment failed due to {req.root_cause}.",
                            "error_source": "bank",
                            "error_reason": req.root_cause,
                            "contact": req.phone,
                            "notes": {"customer_ref": req.phone}
                        }
                    }
                },
                "created_at": int(time.time())
            }
            payload_bytes = json.dumps(payload_dict, separators=(",", ":")).encode("utf-8")
            signature = generate_razorpay_signature(payload_bytes, RAZORPAY_WEBHOOK_SECRET)
            headers = {"Content-Type": "application/json", "X-Razorpay-Signature": signature}
            await client.post(RAZORPAY_WEBHOOK_URL, content=payload_bytes, headers=headers)
            
    background_tasks.add_task(fire_webhook)
    return {"status": "triggered", "phone": req.phone, "persona": req.persona, "root_cause": req.root_cause}

class ManualReplyRequest(BaseModel):
    phone: str
    text: str

@router.post("/reply/manual")
async def sandbox_manual_reply(req: ManualReplyRequest, background_tasks: BackgroundTasks):
    async def fire_webhook():
        async with httpx.AsyncClient() as client:
            await send_whatsapp_webhook(req.phone, req.text, client)
            
    background_tasks.add_task(fire_webhook)
    return {"status": "reply_sent"}

class PersonaReplyRequest(BaseModel):
    case_id: str
    phone: str
    persona: str
    temperature: float = 0.7

@router.post("/reply/persona")
async def sandbox_persona_reply(req: PersonaReplyRequest, session: AsyncSession = Depends(get_db)):
    case_row = await session.scalar(select(Case).where(Case.id == req.case_id))
    if not case_row:
        raise HTTPException(status_code=404, detail="Case not found")
        
    # Build conversation summary
    summary = case_row.raw_payload.get("conversation_summary", "") if case_row.raw_payload else ""
    
    # Get latest agent message
    latest_intervention = await session.scalar(
        select(Intervention).where(Intervention.case_id == req.case_id).order_by(desc(Intervention.sent_at)).limit(1)
    )
    latest_agent_message = latest_intervention.message_sent if latest_intervention else "No message sent yet."
    
    llm_resp = await get_persona_reply(req.persona, summary, latest_agent_message, req.temperature)
    
    # Update case's summary state (usually stored in memory in harness, here we can store in raw_payload)
    new_summary = llm_resp.get("conversation_summary", summary)
    
    if case_row.raw_payload is None:
        case_row.raw_payload = {}
    
    # Shallow copy to trigger sqlalchemy JSON mutation detection
    payload = dict(case_row.raw_payload)
    payload["conversation_summary"] = new_summary
    case_row.raw_payload = payload
    await session.commit()
    
    reply_text = llm_resp.get("reply_text", "")
    if reply_text:
        # Fire inbound webhook
        async with httpx.AsyncClient() as client:
            await send_whatsapp_webhook(req.phone, reply_text, client)
            
    return {"status": "persona_acted", "action": llm_resp.get("action"), "reply": reply_text, "reasoning": llm_resp.get("internal_reasoning")}

class ForceCronRequest(BaseModel):
    case_id: str

@router.post("/force-cron")
async def sandbox_force_cron(req: ForceCronRequest):
    await check_followup(req.case_id, force=True)
    return {"status": "cron_forced"}

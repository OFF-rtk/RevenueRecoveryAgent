#!/usr/bin/env python3
import argparse
import asyncio
import hmac
import hashlib
import json
import os
import sys
import time
import uuid
import random
import httpx
from datetime import datetime
from pathlib import Path

# Ensure the project root is on the path when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from core.models.cases import Case
from core.models.interventions import Intervention
from core.config import settings
from core.llm.client import call_llm
from scripts.trigger_followup import check_followup

# --- Configuration ---
BASE_URL = "https://revenuerecoveryagent.onrender.com"
# BASE_URL = "http://localhost:8001"

RAZORPAY_WEBHOOK_URL = f"{BASE_URL}/webhooks/razorpay"
WHATSAPP_WEBHOOK_URL = f"{BASE_URL}/webhooks/whatsapp"

RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "test_webhook_secret_phase1")
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "test_whatsapp_secret")

PERSONAS = {
    "accidental_failure": "PERSONA: You're a genuinely happy customer of this service. Your payment failure was just an accident -- maybe your card details changed, maybe you weren't paying attention. You have no complaints about the product and no reason to be difficult.\n\nTENDENCY: You generally lean toward paying quickly once you understand what happened and see a clear way to fix it. But you're a real person -- if the message is confusing, you might ask a clarifying question first. If it's clear and easy, you'll likely just pay.",
    "suspicious_payer": "PERSONA: You don't immediately recognize the charge or the product name. You're not hostile, just cautious -- you want to understand what you're being asked to pay for before doing anything.\n\nTENDENCY: You will ask at least one clarifying question first (e.g. \"what product is this for?\", \"when did I sign up for this?\"). If the response you get is clear, specific, and matches something you can plausibly recall signing up for, you lean toward paying. If the response is vague, generic, or doesn't actually answer your question, you become more suspicious and are less likely to pay in this exchange.",
    "needs_payment_help": "PERSONA: Your payment failed because something is wrong with your card on file (expired, wrong details, or similar) -- not because you don't want to pay. You're willing, but you need to actually change your payment method, and you'd prefer an easier option like UPI over re-entering card details.\n\nTENDENCY: You want to pay, but you need the message to actually give you a way to update your details, not just repeat \"please pay\" without addressing the real problem. If offered a clear path to update payment info or use UPI, you're likely to follow through. If the message just blindly asks you to retry the same failed method, you'll push back and ask for an alternative.",
    "considering_cancellation": "PERSONA: You've been thinking about whether you still want this subscription/service at all. The payment failure is a natural moment to reconsider rather than an accident you want fixed immediately.\n\nTENDENCY: You are genuinely on the fence. You might ask what you'd lose by cancelling, express mild hesitation, or ask for more time to decide. A message that clearly communicates value or offers reasonable flexibility might tip you toward paying. A pushy or generic message might tip you toward disengaging. Don't decide in advance which way you'll go -- let the actual conversation determine it.",
    "ignores_completely": "PERSONA: You do not respond to this message at all, under any circumstances, regardless of what it says.\n\nTENDENCY: Always return reply_text as an empty string \"\" and will_pay_now as null. Do not generate any conversational response. This persona exists purely to test the system's behavior when a customer never engages.",
    "forgetful_promises_then_pays": "PERSONA: You're generally willing to pay and not upset about the situation, but you're busy and forgetful. Your natural response to a payment reminder is to say you'll take care of it soon, genuinely intending to -- and then not actually do it right away.\n\nTENDENCY: On first contact, you will make a plausible-sounding promise to pay soon (\"will do it tonight\", \"let me handle this tomorrow\") rather than paying immediately -- always return will_pay_now: null on this first exchange. If and when you receive a FOLLOW-UP message (you'll be told this is a follow-up, not a first message), you lean toward actually paying this time, since a reminder is exactly what you needed -- but you might need the nudge to feel appropriately worded rather than annoying for you to follow through."
}

def generate_razorpay_signature(payload_bytes: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

def generate_whatsapp_signature(payload_bytes: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

async def send_razorpay_webhook(phone: str, client: httpx.AsyncClient):
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
                    "error_description": "Payment failed due to insufficient funds in the account.",
                    "error_source": "bank",
                    "error_reason": "insufficient_funds",
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
    resp = await client.post(RAZORPAY_WEBHOOK_URL, content=payload_bytes, headers=headers)
    return resp

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
    resp = await client.post(RAZORPAY_WEBHOOK_URL, content=payload_bytes, headers=headers)
    return resp

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
    resp = await client.post(WHATSAPP_WEBHOOK_URL, content=payload_bytes, headers=headers)
    return resp

async def get_persona_reply(persona_type: str, conversation_history: list[dict]) -> dict:
    if persona_type == "ignores_completely":
        return {"reply_text": "", "will_pay_now": None}
        
    messages = [
        {"role": "user", "content": f"Your assigned persona is:\n{PERSONAS[persona_type]}"}
    ]
    messages.extend(conversation_history)
    
    res = await call_llm(
        prompt_version="live_harness",
        model=settings.groq_tier1_model,
        user_messages=messages,
        response_format={"type": "json_object"}
    )
    
    try:
        return json.loads(res.content)
    except Exception as e:
        print(f"Error parsing LLM response: {e}")
        return {"reply_text": "", "will_pay_now": None}

async def run_harness(count: int):
    print(f"🚀 Starting Live Persona Harness with {count} cases...")
    
    state_file = Path("data/live_persona_state.json")
    state_file.parent.mkdir(exist_ok=True)
    
    # 1. Initialize Cases
    cases = []
    base_phone = 919000000000
    persona_keys = list(PERSONAS.keys())
    
    # Custom distribution logic
    personas_to_assign = []
    if count == 28:
        personas_to_assign = (
            ["accidental_failure"] * 5 +
            ["suspicious_payer"] * 5 +
            ["needs_payment_help"] * 5 +
            ["considering_cancellation"] * 4 +
            ["ignores_completely"] * 4 +
            ["forgetful_promises_then_pays"] * 5
        )
    elif count == 6:
        personas_to_assign = [
            "accidental_failure",
            "suspicious_payer",
            "needs_payment_help",
            "considering_cancellation",
            "ignores_completely",
            "forgetful_promises_then_pays"
        ]
    else:
        personas_to_assign = [persona_keys[i % len(persona_keys)] for i in range(count)]
        
    random.shuffle(personas_to_assign)
    
    for i in range(count):
        phone = str(base_phone + int(time.time()) % 10000 + i)
        persona = personas_to_assign[i]
        cases.append({
            "phone": phone,
            "persona": persona,
            "status": "active",
            "will_pay": False,
            "replies_sent": 0,
            "seen_interventions": [],
            "conversation": []
        })
        
    # 2. Trigger Razorpay Webhooks
    async with httpx.AsyncClient(timeout=600.0) as client:
        for c in cases:
            print(f"📨 Firing payment.failed for {c['phone']} ({c['persona']})")
            await send_razorpay_webhook(c['phone'], client)
            await asyncio.sleep(0.5) # Rate limit
            
    print("⏳ Waiting 15 seconds for Render to process initial webhooks...")
    await asyncio.sleep(15)
    
    db_url = os.getenv("DATABASE_URL", settings.database_url)
    engine = create_async_engine(db_url)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    MAX_ROUNDS = 10
    
    for round_idx in range(MAX_ROUNDS):
        print(f"\n--- Round {round_idx + 1}/{MAX_ROUNDS} ---")
        active_cases = [c for c in cases if c["status"] == "active"]
        if not active_cases:
            print("No active cases left!")
            break
            
        async with async_session() as session:
            for c in active_cases:
                # Find the Case row for this phone number
                case_row = await session.scalar(
                    select(Case).where(Case.customer_ref == c["phone"]).order_by(desc(Case.created_at)).limit(1)
                )
                if not case_row:
                    continue
                    
                # Get latest Intervention
                intervention = await session.scalar(
                    select(Intervention).where(Intervention.case_id == case_row.id).order_by(desc(Intervention.sent_at)).limit(1)
                )
                
                needs_followup_push = False
                
                if intervention and str(intervention.id) not in c["seen_interventions"]:
                    # New message from the agent!
                    c["seen_interventions"].append(str(intervention.id))
                    agent_text = intervention.message_sent
                    c["conversation"].append({"role": "user", "content": f"Agent says: {agent_text}"})
                    print(f"🤖 Agent -> {c['phone']}: {agent_text}")
                    
                    if c["replies_sent"] >= 5:
                        print(f"🛑 Max replies reached for {c['phone']}. Stalling.")
                        c["status"] = "stalled"
                        continue
                        
                    # Persona LLM responds
                    start_time = time.time()
                    llm_resp = await get_persona_reply(c["persona"], c["conversation"])
                    latency = time.time() - start_time
                    
                    print(f"👤 Persona ({c['persona']}) thought: {llm_resp.get('internal_reasoning')} ({latency:.2f}s)")
                    reply_text = llm_resp.get("reply_text", "").strip()
                    
                    if llm_resp.get("will_pay_now") is True:
                        print(f"💰 Persona {c['phone']} decided to PAY!")
                        c["will_pay"] = True
                        c["status"] = "resolved"
                        async with httpx.AsyncClient(timeout=600.0) as client:
                            await send_payment_captured(c["phone"], client)
                        continue
                        
                    if reply_text:
                        c["replies_sent"] += 1
                        c["conversation"].append({"role": "assistant", "content": reply_text})
                        print(f"📱 Persona -> Agent: {reply_text}")
                        async with httpx.AsyncClient(timeout=600.0) as client:
                            await send_whatsapp_webhook(c["phone"], reply_text, client)
                    else:
                        print(f"🔕 Persona chose to ignore.")
                        needs_followup_push = True
                        
                else:
                    # No new intervention. The app is waiting. We should trigger a follow up!
                    needs_followup_push = True
                    
                if needs_followup_push and c["persona"] != "ignores_completely":
                    # Randomly decide to force a follow-up to advance the stale case
                    if random.random() < 0.5:
                        print(f"⏩ Forcing manual follow-up for {c['phone']} to advance time...")
                        await check_followup(str(case_row.id), force=True)
                        
        print("⏳ Waiting 10 seconds for app to respond...")
        await asyncio.sleep(10)
        
    print("\n📊 Generating Report...")
    report = {
        "summary": {
            "total_cases": len(cases),
            "recovered_cases": sum(1 for c in cases if c["will_pay"]),
            "recovery_rate": f"{(sum(1 for c in cases if c['will_pay']) / len(cases)) * 100:.1f}%",
        },
        "by_persona": {},
        "note": "This report was generated using live deployed infrastructure (real HTTP webhooks against Render) with LLM-simulated persona behavior bypassing the Meta API."
    }
    
    for p_type in PERSONAS.keys():
        p_cases = [c for c in cases if c["persona"] == p_type]
        if not p_cases:
            continue
        p_recovered = sum(1 for c in p_cases if c["will_pay"])
        report["by_persona"][p_type] = {
            "total": len(p_cases),
            "recovered": p_recovered,
            "rate": f"{(p_recovered / len(p_cases)) * 100:.1f}%" if len(p_cases) > 0 else "0%"
        }
        
    report_path = Path("reports/live_persona_report.json")
    report_path.parent.mkdir(exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
        
    print(json.dumps(report, indent=2))
    print(f"\n✅ Done! Report saved to {report_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=3, help="Number of synthetic cases to run")
    args = parser.parse_args()
    asyncio.run(run_harness(args.count))

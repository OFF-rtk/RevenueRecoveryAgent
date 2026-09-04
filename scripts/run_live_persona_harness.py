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

# Line-buffer stdout so progress is visible in real time even when redirected to a file/log
sys.stdout.reconfigure(line_buffering=True)

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from core.models.cases import Case
from core.models.interventions import Intervention
from core.config import settings
from core.llm.client import call_llm
from scripts.trigger_followup import check_followup

# --- Configuration ---
BASE_URL = os.getenv("BASE_URL", "https://revenuerecoveryagent.onrender.com")

RAZORPAY_WEBHOOK_URL = f"{BASE_URL}/webhooks/razorpay"
WHATSAPP_WEBHOOK_URL = f"{BASE_URL}/webhooks/whatsapp"

RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "test_webhook_secret_phase1")
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "test_whatsapp_secret")

PERSONAS = {
    "accidental_failure": "PERSONA: You're a genuinely happy customer of this service. Your payment failure was just an accident -- maybe your card details changed, maybe you weren't paying attention. You have no complaints about the product and no reason to be difficult.\n\nTENDENCY: You generally lean toward paying quickly once you understand what happened and see a clear way to fix it. But you're a real person -- if the message is confusing, you might ask a clarifying question first. If it's clear and easy, you'll likely just pay.",
    "suspicious_payer": "PERSONA: You don't immediately recognize the charge or the product name. You're not hostile, just cautious -- you want to understand what you're being asked to pay for before doing anything.\n\nTENDENCY: You will ask at least one clarifying question first (e.g. \"what product is this for?\", \"when did I sign up for this?\"). If the response you get is clear, specific, and matches something you can plausibly recall signing up for, you lean toward paying. If the response is vague, generic, or doesn't actually answer your question, you become more suspicious and are less likely to pay in this exchange.",
    "needs_payment_help": "PERSONA: Your payment failed because something is wrong with your card on file (expired, wrong details, or similar) -- not because you don't want to pay. You're willing, but you need to actually change your payment method, and you'd prefer an easier option like UPI over re-entering card details.\n\nTENDENCY: You want to pay, but you need the message to actually give you a way to update your details, not just repeat \"please pay\" without addressing the real problem. If the message just blindly asks you to retry the same failed method, you'll push back and ask for an alternative. Even once you're offered a working UPI link or a way to update your card, don't treat that as an automatic done deal -- a real person here might still want to double-check something, get pulled away, or say they'll do it in a minute rather than completing it in the very same exchange. Let whether and when you actually finish paying be a genuine call each time, not a foregone conclusion just because the right option was offered.",
    "considering_cancellation": "PERSONA: You've been thinking about whether you still want this subscription/service at all. The payment failure is a natural moment to reconsider rather than an accident you want fixed immediately.\n\nTENDENCY: You are genuinely on the fence. You might ask what you'd lose by cancelling, express mild hesitation, or ask for more time to decide. A message that clearly communicates value or offers reasonable flexibility might tip you toward paying. A pushy or generic message might tip you toward disengaging. Don't decide in advance which way you'll go -- let the actual conversation determine it.",
    "ignores_completely": "PERSONA: You do not respond to this message at all, under any circumstances, regardless of what it says.\n\nTENDENCY: Always return reply_text as an empty string \"\" and will_pay_now as null. Do not generate any conversational response. This persona exists purely to test the system's behavior when a customer never engages.",
    "forgetful_promises_then_pays": "PERSONA: You're generally willing to pay and not upset about the situation, but you're busy and forgetful. Your natural response to a payment reminder is to say you'll take care of it soon, genuinely intending to -- and then not actually do it right away.\n\nTENDENCY: On first contact, you almost always make a plausible-sounding promise to pay soon (\"will do it tonight\", \"let me handle this tomorrow\") rather than paying immediately -- claiming you're paying right now on the very first message would be out of character. When you later get a FOLLOW-UP message (you'll be told this is a follow-up, not a first message), you're more inclined to actually pay this time, since a reminder is what you needed -- but it's not guaranteed. If the follow-up feels like nagging, arrives without adding anything new, or you're genuinely still caught up in whatever you're doing, you might make yet another vague promise instead. Judge each follow-up on its own merits -- a low-pressure, easy-to-act-on message is what actually tips you into paying, not the mere fact that a reminder arrived."
}

# Realistic, varied payment-failure scenarios. Each is a genuine Razorpay failure mode
# with a free-text error_description -- the app's diagnosis LLM classifies this text into
# one of its own canonical causes (see core/services/diagnosis.py CANONICAL_CAUSES), and
# product_description/payment_method/failure_reason all flow into the agent's reply-drafting
# prompt (core/services/reply_classification.py), so varying these actually changes what the
# agent has to respond to -- not just cosmetic payload noise.
FAILURE_SCENARIOS = [
    {
        "description": "Razorpay Premium Annual Subscription", "amount": 99900, "method": "card",
        "error_code": "BAD_REQUEST_ERROR", "error_reason": "insufficient_funds",
        "error_description": "Payment failed due to insufficient funds in the account.",
    },
    {
        "description": "Razorpay Pro Monthly Plan", "amount": 49900, "method": "card",
        "error_code": "GATEWAY_ERROR", "error_reason": "card_expired",
        "error_description": "The card has expired.",
    },
    {
        "description": "Razorpay Business Suite Subscription", "amount": 299900, "method": "card",
        "error_code": "BAD_REQUEST_ERROR", "error_reason": "incorrect_cvv",
        "error_description": "The CVV entered does not match the card on file.",
    },
    {
        "description": "Razorpay Premium Annual Subscription", "amount": 99900, "method": "card",
        "error_code": "GATEWAY_ERROR", "error_reason": "payment_declined",
        "error_description": "The transaction was declined by the issuing bank.",
    },
    {
        "description": "Razorpay Team Plan Subscription", "amount": 149900, "method": "upi",
        "error_code": "BAD_REQUEST_ERROR", "error_reason": "mandate_cancelled",
        "error_description": "The UPI Autopay mandate for this subscription was revoked by the customer.",
    },
    {
        "description": "Razorpay Pro Monthly Plan", "amount": 49900, "method": "card",
        "error_code": "SERVER_ERROR", "error_reason": "gateway_timeout",
        "error_description": "A temporary gateway timeout occurred while processing the payment.",
    },
]

def generate_razorpay_signature(payload_bytes: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

def generate_whatsapp_signature(payload_bytes: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

async def send_razorpay_webhook(phone: str, client: httpx.AsyncClient, scenario: dict):
    payload_dict = {
        "entity": "event",
        "account_id": "acc_1234567890",
        "event": "payment.failed",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": f"pay_{int(time.time())}_{phone[-4:]}",
                    "amount": scenario["amount"],
                    "currency": "INR",
                    "status": "failed",
                    "method": scenario["method"],
                    "description": scenario["description"],
                    "error_code": scenario["error_code"],
                    "error_description": scenario["error_description"],
                    "error_source": "bank",
                    "error_reason": scenario["error_reason"],
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
    for attempt in range(3):
        try:
            resp = await client.post(RAZORPAY_WEBHOOK_URL, content=payload_bytes, headers=headers)
            return resp
        except Exception as e:
            if attempt == 2:
                raise
            print(f"⚠️ ConnectError in send_razorpay_webhook, retrying ({attempt+1}/3)...")
            await asyncio.sleep(2)

async def send_payment_captured(phone: str, client: httpx.AsyncClient, amount: int = 99900):
    payload_dict = {
        "entity": "event",
        "account_id": "acc_1234567890",
        "event": "payment.captured",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": f"pay_cap_{int(time.time())}_{phone[-4:]}",
                    "amount": amount,
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
    for attempt in range(3):
        try:
            resp = await client.post(RAZORPAY_WEBHOOK_URL, content=payload_bytes, headers=headers)
            return resp
        except Exception as e:
            if attempt == 2:
                raise
            print(f"⚠️ ConnectError in send_payment_captured, retrying ({attempt+1}/3)...")
            await asyncio.sleep(2)

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
    for attempt in range(3):
        try:
            resp = await client.post(WHATSAPP_WEBHOOK_URL, content=payload_bytes, headers=headers)
            return resp
        except Exception as e:
            if attempt == 2:
                raise
            print(f"⚠️ ConnectError in send_whatsapp_webhook, retrying ({attempt+1}/3)...")
            await asyncio.sleep(2)

async def get_persona_reply(persona_type: str, conversation_summary: str, latest_agent_message: str, temperature: float) -> dict:
    if persona_type == "ignores_completely":
        return {"reply_text": "", "action": "undecided", "conversation_summary": conversation_summary}
        
    system_prompt = """You are role-playing as a customer receiving a real WhatsApp message about
a failed payment. Read the actual message shown to you and respond exactly
as this persona would -- in your own words, not a template.

Stay fully in character. Do not mention that you are an AI, a test, or a
simulation under any circumstance.

Your tendencies below describe how you LEAN, not a script you must follow.
Let the specific wording and content of the message you actually receive
genuinely influence your decision in the moment -- a well-handled message
can move you toward paying faster than your default tendency; a confusing
or pushy one can push you the other way. Do not treat your outcome as
predetermined by your persona alone.

Respond with ONLY a JSON object, nothing else:
{
  "reply_text": "string -- what you actually say back, in character",
  "action": "pay_now" | "pause_subscription" | "cancel_or_dispute" | "undecided",
  "internal_reasoning": "string -- brief note on why you responded this way, not shown to the customer-facing system, for our own logging only",
  "conversation_summary": "string -- summarize the ENTIRE conversation history up to and including this turn. This replaces the raw history array."
}

Use "pay_now" only if your reply_text itself indicates you're completing payment right now. 
Use "pause_subscription" if you have explicitly decided to pause the subscription, OR if you asked to pause and the agent agrees to hold/pause it for you (in which case you should accept and pause).
Use "cancel_or_dispute" if you're explicitly declining or disputing. 
Use "undecided" if you're still thinking, asking a question, or deferring to later (e.g. a promise to pay another time).
"""
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Your assigned persona is:\n{PERSONAS[persona_type]}"}
    ]
    
    if conversation_summary:
        messages.append({"role": "user", "content": f"Conversation Summary so far: {conversation_summary}"})
        
    messages.append({"role": "user", "content": f"Latest message from Agent: {latest_agent_message}"})

    headers = {
        "Authorization": f"Bearer {settings.cerebras_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gpt-oss-120b",
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"}
    }
    
    from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
    
    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=20),
        stop=stop_after_attempt(7),
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        reraise=True
    )
    async def _do_post():
        resp = await client.post(f"{settings.cerebras_base_url}/chat/completions", json=payload, headers=headers)
        resp.raise_for_status()
        return resp
        
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await _do_post()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                # Cerebras might not enforce json perfectly
                print(f"Failed to parse JSON, raw content: {content[:100]}...")
                # try to extract a block
                import re
                match = re.search(r"```json(.*?)```", content, re.DOTALL)
                if match:
                    return json.loads(match.group(1).strip())
                raise
        except Exception as e:
            print(f"Error calling Cerebras API: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"Response: {e.response.text}")
            return {"reply_text": "", "action": "undecided", "conversation_summary": conversation_summary}

async def run_harness(count: int, persona_filter: str = None):
    print(f"🚀 Starting Live Persona Harness with {count} cases...")
    
    state_file = Path("data/live_persona_state.json")
    state_file.parent.mkdir(exist_ok=True)
    
    # 1. Initialize Cases
    cases = []
    base_phone = 919000000000
    persona_keys = list(PERSONAS.keys())
    
    # Custom distribution logic
    personas_to_assign = []
    if persona_filter:
        personas_to_assign = [persona_filter] * count
    elif count == 50:
        personas_to_assign = (
            ["considering_cancellation"] * 13 +
            ["needs_payment_help"] * 10 +
            ["accidental_failure"] * 8 +
            ["forgetful_promises_then_pays"] * 7 +
            ["ignores_completely"] * 6 +
            ["suspicious_payer"] * 6
        )
    elif count == 28:
        personas_to_assign = (
            ["accidental_failure"] * 5 +
            ["suspicious_payer"] * 5 +
            ["needs_payment_help"] * 5 +
            ["considering_cancellation"] * 4 +
            ["ignores_completely"] * 4 +
            ["forgetful_promises_then_pays"] * 5
        )
    elif count == 2:
        personas_to_assign = ["considering_cancellation", "considering_cancellation"]
    elif count == 6:
        personas_to_assign = [
            "accidental_failure",
            "suspicious_payer",
            "needs_payment_help",
            "considering_cancellation",
            "ignores_completely",
            "forgetful_promises_then_pays",
        ]
    elif count == 1:
        personas_to_assign = ["suspicious_payer"]
    else:
        personas_to_assign = ["considering_cancellation"] * count
        
    random.shuffle(personas_to_assign)
    
    for i in range(count):
        phone = str(base_phone + int(time.time()) % 10000 + i)
        persona = personas_to_assign[i]
        scenario = random.choice(FAILURE_SCENARIOS)
        cases.append({
            "phone": phone,
            "persona": persona,
            "status": "active",
            "outcome": "active",
            "replies_sent": 0,
            "temperature": round(random.uniform(0.7, 0.9), 2),
            "seen_interventions": [],
            "conversation_summary": "",
            "scenario": scenario
        })

    # 2. Trigger Razorpay Webhooks
    async with httpx.AsyncClient(timeout=60.0) as client:
        for c in cases:
            print(f"📨 Firing payment.failed for {c['phone']} ({c['persona']}, {c['scenario']['error_reason']}, ₹{c['scenario']['amount']/100:.0f})")
            resp = await send_razorpay_webhook(c["phone"], client, c["scenario"])
            if resp.status_code != 200:
                print(f"❌ Webhook failed: {resp.status_code} {resp.text}")
            await asyncio.sleep(8.0) # Rate limit
            
    print("⏳ Waiting 15 seconds for Render to process initial webhooks...")
    await asyncio.sleep(15)
    
    # settings.database_url already normalizes the raw postgres:// scheme to
    # postgresql+asyncpg:// -- reading os.environ directly bypasses that and
    # can crash with "No module named 'psycopg2'" wherever DATABASE_URL is
    # injected in unnormalized form (e.g. Render).
    engine = create_async_engine(settings.database_url, pool_pre_ping=True, pool_recycle=300)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    # 2.5 Log Persona Configuration in Audit Trail
    from core.models.audit_events import AuditEvent
    for attempt in range(5):
        try:
            async with async_session() as session:
                for c in cases:
                    case_row = await session.scalar(
                        select(Case).where(Case.customer_ref == c["phone"]).order_by(desc(Case.created_at)).limit(1)
                    )
                    if case_row:
                        audit_event = AuditEvent(
                            case_id=case_row.id,
                            event_type="persona_simulation_started",
                            payload={
                                "persona": c["persona"],
                                "temperature": c["temperature"],
                                "scenario": c["scenario"]
                            }
                        )
                        session.add(audit_event)
                await session.commit()
            break
        except Exception as e:
            if attempt == 4:
                raise
            print(f"⚠️ DB connection issue during audit logging, retrying ({attempt+1}/5): {e}")
            await asyncio.sleep(5 * (attempt + 1))
    
    MAX_ROUNDS = 40
    
    for round_idx in range(MAX_ROUNDS):
        print(f"\n--- Round {round_idx + 1}/{MAX_ROUNDS} ---")
        active_cases = [c for c in cases if c["status"] == "active"]
        if not active_cases:
            print("No active cases left!")
            break
            
        async with async_session() as session:
            for c in active_cases:
                try:
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
                
                    # Check if we have an unseen intervention
                    has_unseen_intervention = intervention and str(intervention.id) not in c["seen_interventions"]
                
                    # If the DB state is terminal, AND there are no unseen messages for the persona to reply to, we are fully done.
                    if case_row.status in ("recovered", "retained_paused", "stopped", "human_escalated", "timeout") and not has_unseen_intervention:
                        c["status"] = "resolved"
                        c["outcome"] = case_row.status
                        print(f"🏁 Case {c['phone']} reached terminal DB state: {case_row.status} (Conversation concluded)")
                        continue

                    if has_unseen_intervention:
                        # New message from the agent!
                        c["seen_interventions"].append(str(intervention.id))
                        agent_text = intervention.message_sent
                        print(f"🤖 Agent -> {c['phone']}: {agent_text}")
                        
                        max_replies = 12 if c["persona"] == "considering_cancellation" else 10
                        if c["replies_sent"] >= max_replies:
                            print(f"🛑 Max replies reached for {c['phone']}. Stalling.")
                            c["status"] = "stalled"
                            continue
                            
                        # Persona LLM responds
                        start_time = time.time()
                        llm_resp = await get_persona_reply(
                            c["persona"], 
                            c["conversation_summary"], 
                            agent_text,
                            temperature=c["temperature"]
                        )
                        latency = time.time() - start_time
                        
                        c["conversation_summary"] = llm_resp.get("conversation_summary", c["conversation_summary"])
                        
                        print(f"👤 Persona ({c['persona']}) thought: {llm_resp.get('internal_reasoning')} ({latency:.2f}s)")
                        reply_text = llm_resp.get("reply_text", "").strip()
                        action = llm_resp.get("action", "undecided")
                          
                        if action == "pay_now":
                            print(f"💰 Persona {c['phone']} decided to PAY!")
                            # Send webhook so the backend state machine flips it to recovered
                            async with httpx.AsyncClient(timeout=60.0) as client:
                                await send_payment_captured(c["phone"], client, amount=c["scenario"]["amount"])
                            continue
                            
                        elif action == "pause_subscription":
                            print(f"⏸️ Persona {c['phone']} decided to PAUSE!")
                            # The text they generated will be sent to the agent and the agent will classify it as 'paused'.
                            
                        elif action == "cancel":
                            print(f"❌ Persona {c['phone']} decided to CANCEL!")
                            # Text sent to agent will be classified as 'opt_out' -> stopped.
                            
                        if reply_text:
                            c["replies_sent"] += 1
                            print(f"📱 Persona -> Agent: {reply_text}")
                            async with httpx.AsyncClient(timeout=60.0) as client:
                                await send_whatsapp_webhook(c["phone"], reply_text, client)
                        else:
                            print(f"🔕 Persona chose to ignore.")
                            needs_followup_push = True
                            
                    else:
                        # No new intervention. The app is waiting. We should trigger a follow up!
                        needs_followup_push = True
                        
                    if needs_followup_push:
                        # Randomly decide to force a follow-up to advance the stale case
                        if random.random() < 0.5:
                            print(f"⏩ Forcing manual follow-up for {c['phone']} to advance time...")
                            # use_mock=True: this harness explicitly bypasses the real Meta WhatsApp
                            # API (see report note below) -- synthetic 919000... numbers were never
                            # added to Meta's sandbox allow-list, so a real send here can only fail.
                            await check_followup(str(case_row.id), force=True, use_mock=True)
                
                except Exception as e:
                    print(f"⚠️ Unhandled error for case {c['phone']}: {e}")
                    import traceback
                    traceback.print_exc()
                    try:
                        await session.rollback()
                    except Exception as rollback_err:
                        print(f"⚠️ Rollback also failed: {rollback_err}")
                    # Transient DB/network errors shouldn't permanently give up on a case --
                    # leave it active so it gets retried next round instead of poisoning
                    # the shared session for every case still to be processed this round.

            # Incremental save per round
            with open(state_file, "w") as f:
                json.dump(cases, f, indent=2)
                        
        print("⏳ Waiting 10 seconds for app to respond...")
        await asyncio.sleep(10)
        
    # Final sweep: Check DB status for any remaining cases
    async with async_session() as session:
        for c in cases:
            if c["status"] in ["active", "stalled"]:
                case_row = await session.scalar(
                    select(Case).where(Case.customer_ref == c["phone"]).order_by(desc(Case.created_at)).limit(1)
                )
                if case_row and case_row.status in ("recovered", "retained_paused", "stopped", "human_escalated", "timeout"):
                    c["outcome"] = case_row.status
                else:
                    c["outcome"] = "timeout" # Default to timeout
                c["status"] = "resolved"

    print("\n📊 Generating Report...")
    total = len(cases)
    
    def calc_pct(c_list, condition):
        if not c_list: return "0.0%"
        return f"{(sum(1 for c in c_list if condition(c)) / len(c_list)) * 100:.1f}%"
        
    report = {
        "summary": {
            "total_cases": total,
            "outcomes": {
                "recovered": sum(1 for c in cases if c["outcome"] == "recovered"),
                "retained_paused": sum(1 for c in cases if c["outcome"] == "retained_paused"),
                "human_escalated": sum(1 for c in cases if c["outcome"] == "human_escalated"),
                "stopped": sum(1 for c in cases if c["outcome"] == "stopped"),
                "timeout": sum(1 for c in cases if c["outcome"] == "timeout"),
                "error": sum(1 for c in cases if c["outcome"] == "error")
            },
            "percentages": {
                "recovered": calc_pct(cases, lambda c: c["outcome"] == "recovered"),
                "retained_paused": calc_pct(cases, lambda c: c["outcome"] == "retained_paused"),
                "human_escalated": calc_pct(cases, lambda c: c["outcome"] == "human_escalated"),
                "stopped": calc_pct(cases, lambda c: c["outcome"] == "stopped"),
                "timeout": calc_pct(cases, lambda c: c["outcome"] == "timeout"),
                "error": calc_pct(cases, lambda c: c["outcome"] == "error")
            },
            "kpis": {
                "recovery_rate": calc_pct(cases, lambda c: c["outcome"] == "recovered"),
                "retention_rate": calc_pct(cases, lambda c: c["outcome"] in ["recovered", "retained_paused"])
            }
        },
        "by_persona": {},
        "cases_data": cases,
        "note": "This report was generated using live deployed infrastructure (real HTTP webhooks against Render) with LLM-simulated persona behavior bypassing the Meta API."
    }
    
    for p_type in PERSONAS.keys():
        p_cases = [c for c in cases if c["persona"] == p_type]
        if not p_cases:
            continue
            
        report["by_persona"][p_type] = {
            "total": len(p_cases),
            "outcomes": {
                "recovered": sum(1 for c in p_cases if c["outcome"] == "recovered"),
                "retained_paused": sum(1 for c in p_cases if c["outcome"] == "retained_paused"),
                "human_escalated": sum(1 for c in p_cases if c["outcome"] == "human_escalated"),
                "stopped": sum(1 for c in p_cases if c["outcome"] == "stopped"),
                "timeout": sum(1 for c in p_cases if c["outcome"] == "timeout"),
                "error": sum(1 for c in p_cases if c["outcome"] == "error")
            },
            "percentages": {
                "recovered": calc_pct(p_cases, lambda c: c["outcome"] == "recovered"),
                "retained_paused": calc_pct(p_cases, lambda c: c["outcome"] == "retained_paused"),
                "human_escalated": calc_pct(p_cases, lambda c: c["outcome"] == "human_escalated"),
                "stopped": calc_pct(p_cases, lambda c: c["outcome"] == "stopped"),
                "timeout": calc_pct(p_cases, lambda c: c["outcome"] == "timeout"),
                "error": calc_pct(p_cases, lambda c: c["outcome"] == "error")
            },
            "kpis": {
                "recovery_rate": calc_pct(p_cases, lambda c: c["outcome"] == "recovered"),
                "retention_rate": calc_pct(p_cases, lambda c: c["outcome"] in ["recovered", "retained_paused"])
            }
        }
        
    report_path = Path("reports/live_persona_report.json")
    report_path.parent.mkdir(exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
        
    print(json.dumps({k: v for k, v in report.items() if k != "cases_data"}, indent=2))
    print(f"\n✅ Done! Report saved to {report_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=3, help="Number of synthetic cases to run")
    parser.add_argument("--persona", type=str, default=None, help="Specific persona to test")
    args = parser.parse_args()
    asyncio.run(run_harness(args.count, args.persona))

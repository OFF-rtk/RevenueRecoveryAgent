#!/usr/bin/env python3
"""
scripts/run_e2e_simulation.py
──────────────────────────────
End-to-End HTTP Simulation Engine

Reads synthetic cases from a JSON fixtures file and interacts with the running
FastAPI application over HTTP to test the full webhook lifecycle.

Usage:
    .venv/bin/python scripts/run_e2e_simulation.py --fixtures fixtures/mini_fixtures.json --url http://localhost:8000
"""
from __future__ import annotations

import argparse
import asyncio
import hmac
import hashlib
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import settings
from core.db import async_session_factory, init_db
from sqlalchemy import select
from core.models.cases import Case

def sign_payload(payload: dict, secret: str) -> str:
    body_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    return hmac.new(
        secret.encode("utf-8"),
        body_bytes,
        hashlib.sha256
    ).hexdigest()

async def get_case_status(case_id: str) -> str:
    factory = async_session_factory()
    async with factory() as session:
        case = await session.get(Case, case_id)
        return case.status if case else "unknown"

async def clear_db():
    from core.db import engine
    from core.models.base import Base
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            # Use raw SQL to clear without dropping tables (truncate might fail on FKs in sqlite, but delete works)
            await conn.execute(table.delete())

async def run_simulation(fixtures_file: str, base_url: str):
    with open(fixtures_file, "r") as f:
        cases_data = json.load(f)

    stats = {
        "total_cases": len(cases_data),
        "amount_at_risk": 0,
        "amount_recovered": 0,
        "outcomes": {
            "recovered": 0,
            "escalated": 0,
            "disputed": 0,
            "stopped": 0,
            "open": 0,
        },
    }

    # Initialize DB connection to poll status
    await init_db(settings.database_url)
    
    # We clear the DB for E2E just like --fresh in run_batch
    await clear_db()

    async with httpx.AsyncClient(base_url=base_url) as client:
        for i, case_data in enumerate(cases_data):
            case_id = case_data["id"]
            amount = case_data["amount"]
            currency = case_data["currency"]
            
            stats["amount_at_risk"] += amount
            
            # 1. Send Razorpay payment.failed webhook
            failed_payload = {
                "entity": "event",
                "account_id": "acc_123",
                "event": "payment.failed",
                "contains": ["payment"],
                "payload": {
                    "payment": {
                        "entity": {
                            "id": f"pay_{case_id}",
                            "amount": amount,
                            "currency": currency,
                            "status": "failed",
                            "error_code": case_data["error_code"],
                            "error_description": case_data["error_description"],
                            "contact": "+1234567890",
                            "email": "test@example.com"
                        }
                    }
                },
                "created_at": int(time.time())
            }
            
            body_str = json.dumps(failed_payload, separators=(',', ':'))
            signature = sign_payload(failed_payload, settings.razorpay_webhook_secret)
            
            r = await client.post(
                "/webhooks/razorpay", 
                content=body_str.encode('utf-8'),
                headers={"X-Razorpay-Signature": signature, "Content-Type": "application/json"}
            )
            r.raise_for_status()
            
            # Poll for background diagnosis/intervention
            status = "open"
            for _ in range(15): # wait up to 15s
                status = await get_case_status(case_id)
                if status != "open":
                    break
                await asyncio.sleep(1.0)
                
            reply_text = case_data.get("reply_text")
            if reply_text:
                # 2. Send WhatsApp inbound webhook
                wa_payload = {
                    "object": "whatsapp_business_account",
                    "entry": [{
                        "id": "123456789",
                        "changes": [{
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "16505551111",
                                    "phone_number_id": "123456789"
                                },
                                "contacts": [{
                                    "profile": {"name": "Test User"},
                                    "wa_id": "+1234567890"
                                }],
                                "messages": [{
                                    "from": "+1234567890",
                                    "id": f"wamid_{case_id}",
                                    "timestamp": str(int(time.time())),
                                    "text": {"body": reply_text},
                                    "type": "text"
                                }]
                            },
                            "field": "messages"
                        }]
                    }]
                }
                
                r = await client.post("/webhooks/whatsapp", json=wa_payload)
                r.raise_for_status()
                
                # Wait for state machine to process
                await asyncio.sleep(2.0)
                
            # 3. Simulate Recovery if applicable
            outcome_path = case_data.get("outcome_path", "")
            status = await get_case_status(case_id)
            
            should_recover = (
                (status == "promise_pending" and outcome_path == "resolved_via_reply")
                or outcome_path == "resolved_via_webhook"
            )
            
            if should_recover:
                captured_payload = {
                    "entity": "event",
                    "account_id": "acc_123",
                    "event": "payment.captured",
                    "contains": ["payment"],
                    "payload": {
                        "payment": {
                            "entity": {
                                "id": f"pay_{case_id}_captured",
                                "amount": amount,
                                "currency": currency,
                                "status": "captured",
                                "contact": "+1234567890",
                                "email": "test@example.com",
                                "notes": {
                                    "recovery_case_id": case_id
                                }
                            }
                        }
                    },
                    "created_at": int(time.time())
                }
                body_str = json.dumps(captured_payload, separators=(',', ':'))
                signature = sign_payload(captured_payload, settings.razorpay_webhook_secret)
                
                r = await client.post(
                    "/webhooks/razorpay", 
                    content=body_str.encode('utf-8'),
                    headers={"X-Razorpay-Signature": signature, "Content-Type": "application/json"}
                )
                r.raise_for_status()
                await asyncio.sleep(1.0)
                
            final_status = await get_case_status(case_id)
            
            if final_status in ("open", "promise_pending", "pending_reply"):
                final_status = "open"
                
            if final_status in stats["outcomes"]:
                stats["outcomes"][final_status] += 1
            else:
                stats["outcomes"]["open"] += 1
                
            if final_status == "recovered":
                stats["amount_recovered"] += amount
                
            print(f"  Processed {i+1}/{len(cases_data)} cases. [{case_id}: {final_status}]", file=sys.stderr)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 7 — E2E Simulation Engine")
    parser.add_argument("--fixtures", type=str, required=True, help="Path to JSON fixtures file")
    parser.add_argument("--url", type=str, default="http://localhost:8000", help="Base URL of FastAPI app")
    args = parser.parse_args()

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  Revenue Recovery Agent — E2E Simulation Engine", file=sys.stderr)
    print(f"  Fixtures: {args.fixtures} | URL: {args.url}", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    start = time.monotonic()
    stats = asyncio.run(run_simulation(args.fixtures, args.url))
    elapsed = time.monotonic() - start

    stats["elapsed_seconds"] = round(elapsed, 1)
    stats["amount_at_risk"] = str(stats["amount_at_risk"])
    stats["amount_recovered"] = str(stats["amount_recovered"])

    output = json.dumps(stats, indent=2, default=str)
    print(output)

    print(f"\n  Done in {elapsed:.1f}s. Pipe output to scripts/generate_report.py or save to a file.", file=sys.stderr)


if __name__ == "__main__":
    main()

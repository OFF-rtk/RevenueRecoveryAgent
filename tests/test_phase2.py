"""
tests/test_phase2.py
────────────────────
Phase 2 test checklist:
  [1] Fixture payloads for each of the 3-4 real event types map to the correct
      case_type with correct fields extracted.
  [2] A malformed or unexpected payload is logged clearly and does not take down
      the ingestion endpoint.
  [3] Run the full Phase 1 + 2 pipeline against 10 fixture payloads and confirm
      10/10 land in cases with correct types.
"""
from __future__ import annotations

import json
from decimal import Decimal

import pytest
from sqlalchemy import select

from core.models.cases import Case

# ── Helpers ──────────────────────────────────────────────────────────────────

def _post_webhook(client, secret: str, payload_dict: dict) -> dict:
    from tests.test_phase1 import _make_signature
    raw_body = json.dumps(payload_dict, separators=(",", ":")).encode()
    signature = _make_signature(raw_body, secret)
    resp = client.post(
        "/webhooks/razorpay",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature,
        },
    )
    return resp

def _base_payload(event: str, entity_name: str, entity_id: str, fields: dict) -> dict:
    return {
        "event": event,
        "payload": {
            entity_name: {
                "entity": {
                    "id": entity_id,
                    **fields
                }
            }
        }
    }


# ── Tests ────────────────────────────────────────────────────────────────────

@pytest.mark.integration
async def test_event_mapping_correctness(webhook_secret, db_session):
    """
    Test that different Razorpay event types map to the correct case_type
    and extract fields correctly.
    """
    from core.webhooks.razorpay import process_webhook
    from tests.test_phase1 import _make_signature

    events = [
        ("payment.failed", "payment", "pay_01", {"amount": 10000, "email": "a@a.com", "error_code": "CARD_EXPIRED"}, "failed_subscription"),
        ("subscription.pending", "subscription", "sub_02", {"amount": 5000, "contact": "9999999999", "status": "pending"}, "failed_subscription"),
        ("subscription.halted", "subscription", "sub_03", {"amount": 5000, "customer_id": "cust_03", "status": "halted"}, "failed_subscription"),
        ("invoice.expired", "invoice", "inv_04", {"amount_due": 20000, "email": "d@d.com", "status": "expired"}, "overdue_receivable"),
        ("invoice.partially_paid", "invoice", "inv_05", {"amount_due": 5000, "email": "e@e.com", "status": "partially_paid"}, "overdue_receivable"),
    ]

    case_ids = []
    for event, entity_name, entity_id, fields, expected_type in events:
        payload = _base_payload(event, entity_name, entity_id, fields)
        raw_body = json.dumps(payload, separators=(",", ":")).encode()
        signature = _make_signature(raw_body, webhook_secret)
        
        data = await process_webhook(
            raw_body=raw_body,
            signature=signature,
            payload=payload,
            secret=webhook_secret,
            session=db_session
        )
        assert data["status"] == "ok"
        assert data["case_type"] == expected_type
        case_ids.append(data["case_id"])

    # Verify extracted fields in DB
    cases = (await db_session.scalars(select(Case).where(Case.id.in_(case_ids)))).all()
    assert len(cases) == 5

    cases_by_id = {str(c.id): c for c in cases}
    
    # Check inv_04 (invoice.expired)
    inv04_case_id = case_ids[3]
    c_inv04 = cases_by_id[inv04_case_id]
    assert c_inv04.case_type == "overdue_receivable"
    assert c_inv04.amount == Decimal("200.00")  # 20000 paise
    assert c_inv04.customer_ref == "d@d.com"
    assert c_inv04.raw_failure_reason == "expired"
    assert c_inv04.razorpay_event_id == "invoice.expired:inv_04"


def test_malformed_payload_logged_and_skipped(fastapi_client, webhook_secret):
    """
    A payload missing expected entity structures should not crash the server.
    It should return 200 with {"status": "ignored"} to prevent infinite retries.
    """
    # Missing payload.payment.entity.id
    bad_payload = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "amount": 10000
                }
            }
        }
    }
    
    resp = _post_webhook(fastapi_client, webhook_secret, bad_payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
    assert "malformed payload" in resp.json().get("reason", "")


@pytest.mark.integration
def test_ten_fixtures_pipeline(fastapi_client, webhook_secret):
    """
    Run 10 fixture payloads and confirm 10/10 land correctly.
    """
    payloads = []
    for i in range(10):
        # alternate between payment.failed and invoice.expired
        if i % 2 == 0:
            payloads.append(_base_payload(
                "payment.failed", "payment", f"pay_batch_{i}",
                {"amount": (i+1)*1000, "email": f"user{i}@test.com", "error_code": "FAILED"}
            ))
        else:
            payloads.append(_base_payload(
                "invoice.expired", "invoice", f"inv_batch_{i}",
                {"amount_due": (i+1)*1000, "email": f"user{i}@test.com", "status": "expired"}
            ))
            
    successes = 0
    for payload in payloads:
        resp = _post_webhook(fastapi_client, webhook_secret, payload)
        if resp.status_code == 200 and resp.json().get("status") == "ok":
            successes += 1
            
    assert successes == 10, f"Expected 10 successes, got {successes}"

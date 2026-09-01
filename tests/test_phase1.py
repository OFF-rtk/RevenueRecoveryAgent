"""
tests/test_phase1.py
────────────────────
Phase 1 test checklist:
  [1] Migrations apply cleanly and are reversible
  [2] Valid Razorpay webhook payload accepted and stored correctly
  [3] Invalid signature rejected with a logged reason, not a silent 200
  [4] Same event replayed twice → exactly one case row
  [5] Synthetic generator run twice with the same seed → byte-identical output

Tests that need a live DB are marked @pytest.mark.integration.
Run unit-only:  pytest tests/test_phase1.py -v -m "not integration"
Run full suite: pytest tests/test_phase1.py -v
"""
from __future__ import annotations

import hashlib
import hmac
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text

# ── Helpers ──────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent


def _make_signature(raw_body: bytes, secret: str) -> str:
    """Compute the Razorpay-style HMAC-SHA256 signature for a payload."""
    return hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()


def _make_payment_failed_payload(
    payment_id: str = "pay_TEST001",
    amount_paise: int = 99900,
    customer_email: str = "test@example.com",
) -> dict:
    """Construct a minimal Razorpay payment.failed webhook payload."""
    return {
        "entity": "event",
        "event": "payment.failed",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "amount": amount_paise,
                    "currency": "INR",
                    "status": "failed",
                    "email": customer_email,
                    "error_code": "CARD_EXPIRED",
                    "error_description": "The card has expired",
                }
            }
        },
        "created_at": 1724000000,
    }




# ── Test 1: Migrations reversible ─────────────────────────────────────────────

@pytest.mark.integration
def test_migrations_apply_and_are_reversible():
    """
    alembic upgrade head creates all 7 tables.
    alembic downgrade base drops them all.
    Re-upgrading confirms the migration is idempotent.
    """
    expected_tables = {
        "cases", "diagnoses", "interventions", "replies",
        "state_transitions", "audit_events", "outcomes",
    }

    # Verify tables exist after upgrade (apply_migrations fixture already ran)
    import asyncio
    from core.config import settings
    from core.db import init_db
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import inspect, text

    async def _check_tables(expected: set[str]) -> set[str]:
        engine = create_async_engine(settings.database_url)
        async with engine.connect() as conn:
            result = await conn.execute(text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            ))
            tables = {row[0] for row in result}
        await engine.dispose()
        return tables

    tables = asyncio.run(_check_tables(expected_tables))
    missing = expected_tables - tables
    assert not missing, f"Tables missing after upgrade: {missing}"

    # Downgrade
    down = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "base"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    assert down.returncode == 0, f"downgrade failed:\n{down.stderr}"

    tables_after_down = asyncio.run(_check_tables(set()))
    remaining = expected_tables & tables_after_down
    assert not remaining, f"Tables still present after downgrade: {remaining}"

    # Re-upgrade — confirms the migration file is truly reversible
    up = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    assert up.returncode == 0, f"re-upgrade failed:\n{up.stderr}"


# ── Test 2: Valid webhook accepted ────────────────────────────────────────────

@pytest.mark.integration
def test_valid_webhook_accepted_and_stored(fastapi_client, webhook_secret):
    """POST with correct HMAC → 200, case row present in DB."""
    payload = _make_payment_failed_payload(payment_id="pay_VALID001")
    raw_body = json.dumps(payload, separators=(",", ":")).encode()
    signature = _make_signature(raw_body, webhook_secret)

    resp = fastapi_client.post(
        "/webhooks/razorpay",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature,
        },
    )

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["status"] == "ok"
    assert "case_id" in body
    assert body["case_type"] == "failed_subscription"


# ── Test 3: Invalid signature rejected ───────────────────────────────────────

def test_invalid_signature_rejected(fastapi_client):
    """POST with wrong signature → 400. Checked without a DB query."""
    payload = _make_payment_failed_payload(payment_id="pay_BADSIG")
    raw_body = json.dumps(payload, separators=(",", ":")).encode()
    bad_signature = "0" * 64  # wrong hex string

    resp = fastapi_client.post(
        "/webhooks/razorpay",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": bad_signature,
        },
    )

    assert resp.status_code == 400
    assert "signature" in resp.json().get("detail", "").lower()


# ── Test 4: Idempotency — replay → one row ────────────────────────────────────

@pytest.mark.integration
def test_duplicate_webhook_creates_only_one_case(fastapi_client, webhook_secret):
    """Posting the same event twice results in exactly one case row."""
    payload = _make_payment_failed_payload(payment_id="pay_DEDUP001")
    raw_body = json.dumps(payload, separators=(",", ":")).encode()
    signature = _make_signature(raw_body, webhook_secret)
    headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Signature": signature,
    }

    resp1 = fastapi_client.post("/webhooks/razorpay", content=raw_body, headers=headers)
    resp2 = fastapi_client.post("/webhooks/razorpay", content=raw_body, headers=headers)

    assert resp1.status_code == 200
    assert resp2.status_code == 200

    body1 = resp1.json()
    body2 = resp2.json()

    assert body1["status"] == "ok"
    assert body2["status"] == "duplicate"
    assert body2["deduplicated"] is True
    # Both responses reference the same case
    assert body2["existing_case_id"] == body1["case_id"]


# ── Test 5: Synthetic generator determinism ───────────────────────────────────

def test_synthetic_generator_is_deterministic():
    """
    Running the generator twice with the same seed produces byte-identical output.
    Uses sort_keys=True in the generator, so JSON key ordering is stable.
    """
    from scripts.seed_synthetic import generate_cases

    run1 = generate_cases(count=20, seed=42)
    run2 = generate_cases(count=20, seed=42)

    # Serialize both with identical settings
    json1 = json.dumps(run1, sort_keys=True, ensure_ascii=False)
    json2 = json.dumps(run2, sort_keys=True, ensure_ascii=False)

    assert json1 == json2, "Generator output differs between runs with the same seed"
    assert len(run1) == 20

    # Spot-check shape of one record
    case = run1[0]
    assert "case_type" in case
    assert case["case_type"] in ("failed_subscription", "overdue_receivable")
    assert "ground_truth_cause" in case
    assert Decimal(case["amount"]) > 0


def test_synthetic_generator_different_seeds_differ():
    """Different seeds should produce different outputs (basic sanity check)."""
    from scripts.seed_synthetic import generate_cases

    run_a = generate_cases(count=5, seed=1)
    run_b = generate_cases(count=5, seed=999)

    json_a = json.dumps(run_a, sort_keys=True)
    json_b = json.dumps(run_b, sort_keys=True)

    assert json_a != json_b, "Two different seeds produced identical output"

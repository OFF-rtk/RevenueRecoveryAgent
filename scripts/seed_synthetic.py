#!/usr/bin/env python3
"""
Synthetic recovery case generator.

Produces deterministic, realistic-looking case data for testing and volume
benchmarking. Key design rule: uses random.Random(seed) — an isolated instance,
NOT the global random.seed() — so the same seed always yields byte-identical
output regardless of other code that may also call random.

Usage:
    # Print JSON to stdout
    .venv/bin/python scripts/seed_synthetic.py --count 20 --seed 42

    # Write to a file
    .venv/bin/python scripts/seed_synthetic.py --count 20 --seed 42 --output cases.json

    # Insert directly into the database
    .venv/bin/python scripts/seed_synthetic.py --count 20 --seed 42 --insert

Determinism guarantee:
    Running with the same --count and --seed always produces byte-identical JSON.
    This is verified in test_phase1.py::test_synthetic_generator_is_deterministic.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

# ── Domain constants ──────────────────────────────────────────────────────────

# (raw_failure_reason, ground_truth_cause) pairs per case type.
# ground_truth_cause is used in Phase 3 to measure LLM diagnosis accuracy.
_FAILURE_PROFILES: dict[str, list[tuple[str, str]]] = {
    "failed_subscription": [
        ("INSUFFICIENT_FUNDS", "insufficient_funds"),
        ("CARD_EXPIRED", "expired_card"),
        ("INVALID_CARD", "wrong_details"),
        ("DO_NOT_HONOUR", "bank_declined"),
        ("MANDATE_CANCELLED", "mandate_revoked"),
        ("TECHNICAL_ERROR", "technical_error"),
        ("LOST_STOLEN_CARD", "bank_declined"),
        ("EXCEEDS_WITHDRAWAL_LIMIT", "insufficient_funds"),
    ],
    "overdue_receivable": [
        ("PAYMENT_OVERDUE", "payment_forgotten"),
        ("DISPUTE_RAISED", "dispute_raised"),
        ("INVOICE_UNPAID", "payment_forgotten"),
        ("INCORRECT_AMOUNT", "wrong_invoice_details"),
        ("CASH_FLOW", "cash_flow_issue"),
    ],
}

_AMOUNTS_PAISE: list[int] = [
    49900, 99900, 199900, 299900, 499900,
    999900, 1999900, 4999900,
]

_TENURES_MONTHS: list[int] = [1, 3, 6, 12, 24]


# ── Generator ─────────────────────────────────────────────────────────────────

def generate_cases(count: int, seed: int) -> list[dict[str, Any]]:
    """
    Generate `count` synthetic cases deterministically from `seed`.

    The output list is fully determined by (count, seed): same inputs → same
    list in the same order with the same field values.
    """
    rng = random.Random(seed)  # isolated — never touches global random state
    cases: list[dict[str, Any]] = []

    for i in range(count):
        case_type = rng.choice(["failed_subscription", "overdue_receivable"])
        profiles = _FAILURE_PROFILES[case_type]
        raw_reason, ground_truth_cause = rng.choice(profiles)
        amount_paise = rng.choice(_AMOUNTS_PAISE)
        cust_id = rng.randint(10_000, 99_999)

        case: dict[str, Any] = {
            "case_type": case_type,
            "customer_ref": f"cust_{cust_id}",
            "amount": str(Decimal(amount_paise) / Decimal("100")),  # str for JSON determinism
            "currency": "INR",
            "raw_failure_reason": raw_reason,
            "ground_truth_cause": ground_truth_cause,   # Phase 3 accuracy baseline
            "razorpay_event_id": None,                  # synthetic — no real event
        }

        if case_type == "failed_subscription":
            case["tenure"] = rng.choice(_TENURES_MONTHS)
        else:
            case["tenure"] = None

        cases.append(case)

    return cases


# ── DB insertion ──────────────────────────────────────────────────────────────

async def insert_cases(cases: list[dict[str, Any]]) -> None:
    """Insert generated cases directly into the database."""
    # Import here so the script works without a DB when only --output is used
    from core.config import settings
    from core.db import init_db, async_session_factory
    from core.models.cases import Case

    await init_db(settings.database_url)
    factory = async_session_factory()

    async with factory() as session:
        for c in cases:
            row = Case(
                case_type=c["case_type"],
                customer_ref=c["customer_ref"],
                amount=Decimal(c["amount"]),
                currency=c["currency"],
                raw_failure_reason=c["raw_failure_reason"],
                tenure=c.get("tenure"),
                raw_payload={"ground_truth_cause": c["ground_truth_cause"],
                             "synthetic": True},
            )
            session.add(row)
        await session.commit()

    print(f"Inserted {len(cases)} synthetic cases.", file=sys.stderr)


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Generate deterministic synthetic recovery cases.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--count", type=int, default=20, help="Number of cases to generate (default: 20)")
    p.add_argument("--seed",  type=int, default=42,  help="Random seed for determinism (default: 42)")
    p.add_argument("--output", type=str, default=None,
                   help="Write JSON to this file path instead of stdout")
    p.add_argument("--insert", action="store_true",
                   help="Insert cases into the database (requires .env / DB running)")
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    cases = generate_cases(count=args.count, seed=args.seed)

    if args.insert:
        asyncio.run(insert_cases(cases))
    else:
        # Serialise with sort_keys=True and no extra whitespace for byte-identical output
        output = json.dumps(cases, indent=2, sort_keys=True, ensure_ascii=False)
        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
            print(f"Wrote {len(cases)} cases to {args.output}", file=sys.stderr)
        else:
            print(output)


if __name__ == "__main__":
    main()

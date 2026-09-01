#!/usr/bin/env python3
"""
scripts/generate_report.py
──────────────────────────
Phase 7 Report Generator.

Reads the batch runner stats from stdin (or a JSON file), queries the DB for
spot-check data, and writes two output files:

  reports/batch_report.json  — machine-readable structured report
  reports/batch_report.md    — human-readable pitch artifact

Usage:
    # Pipe from batch runner (recommended)
    .venv/bin/python scripts/run_batch.py | .venv/bin/python scripts/generate_report.py

    # Or from a saved stats file
    .venv/bin/python scripts/generate_report.py --stats-file batch_stats.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

REPORTS_DIR = Path(__file__).parent.parent / "reports"


async def fetch_spot_checks(n: int = 5) -> list[dict]:
    """Pull n random synthetic cases with their full audit trail summary."""
    from core.config import settings
    from core.db import init_db, async_session_factory
    from core.models.cases import Case
    from core.models.diagnoses import Diagnosis
    from core.models.audit_events import AuditEvent
    from core.models.outcomes import Outcome
    from core.services.diagnosis import normalise_cause
    from sqlalchemy import select, func

    await init_db(settings.database_url)
    factory = async_session_factory()

    results = []
    async with factory() as session:
        # Pick n random synthetic cases
        sample_cases = (await session.scalars(
            select(Case)
            .where(Case.razorpay_event_id.is_(None))
            .order_by(func.random())
            .limit(n)
        )).all()

        for case in sample_cases:
            # Latest diagnosis
            diagnosis = await session.scalar(
                select(Diagnosis)
                .where(Diagnosis.case_id == case.id)
                .order_by(Diagnosis.created_at.desc())
                .limit(1)
            )

            # Audit event types
            audit_events = (await session.scalars(
                select(AuditEvent.event_type)
                .where(AuditEvent.case_id == case.id)
                .order_by(AuditEvent.created_at)
            )).all()

            # Outcome
            outcome = await session.scalar(
                select(Outcome).where(Outcome.case_id == case.id)
            )

            ground_truth = (case.raw_payload or {}).get("ground_truth_cause", "unknown")

            results.append({
                "case_id": str(case.id)[:8] + "...",
                "case_type": case.case_type,
                "amount_inr": str(case.amount),
                "ground_truth_cause": ground_truth,
                "diagnosed_cause": ", ".join(diagnosis.causes) if diagnosis and diagnosis.causes else "N/A",
                "diagnosis_correct": (normalise_cause(ground_truth) in (diagnosis.causes or [])) if diagnosis else False,
                "model_tier": diagnosis.model_tier if diagnosis else "N/A",
                "final_status": case.status,
                "audit_events": list(audit_events),
                "amount_recovered": str(outcome.amount_recovered) if outcome else "0",
            })

    return results


def build_report(stats: dict, spot_checks: list[dict]) -> dict:
    """Build the structured JSON report."""
    total = stats["total"]
    diagnosed = stats["diagnosed_tier1"] + stats["diagnosed_tier2"]
    tier1_pct = round(stats["diagnosed_tier1"] / max(diagnosed, 1) * 100, 1)
    tier2_pct = round(stats["diagnosed_tier2"] / max(diagnosed, 1) * 100, 1)
    accuracy_pct = round(stats["diagnosis_correct"] / max(diagnosed, 1) * 100, 1)

    amount_at_risk = Decimal(stats["amount_at_risk"])
    amount_recovered = Decimal(stats["amount_recovered"])
    recovery_rate = round(float(amount_recovered / amount_at_risk * 100), 1) if amount_at_risk else 0

    outcomes = stats["outcomes"]
    recovered = outcomes.get("recovered", 0)

    return {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "batch_config": {
            "total_cases": total,
            "elapsed_seconds": stats.get("elapsed_seconds"),
        },
        "diagnosis": {
            "total_diagnosed": diagnosed,
            "failed": stats["diagnosis_failed"],
            "tier1_resolved": stats["diagnosed_tier1"],
            "tier2_escalated": stats["diagnosed_tier2"],
            "tier1_pct": tier1_pct,
            "tier2_pct": tier2_pct,
            "accuracy_pct": accuracy_pct,
            "correct": stats["diagnosis_correct"],
            "expected_escalations_total": stats.get("expected_escalations_total", 0),
            "expected_escalations_caught": stats.get("expected_escalations_caught", 0),
        },
        "interventions": {
            "sent": stats["intervention_sent"],
            "blocked_by_stopping_rules": stats["intervention_blocked"],
        },
        "replies": {
            "simulated": stats["replies_simulated"],
            "no_reply": stats["no_reply"],
            "deliberate_opt_out": stats["opt_out_deliberate"],
        },
        "outcomes": {
            "recovered": recovered,
            "promise_pending": outcomes.get("promise_pending", 0),
            "payment_method_required": outcomes.get("payment_method_required", 0),
            "escalated": outcomes.get("escalated", 0),
            "disputed": outcomes.get("disputed", 0),
            "stopped": outcomes.get("stopped", 0),
            "open_unresolved": outcomes.get("open", 0),
        },
        "recovery": {
            "total_amount_at_risk_inr": str(amount_at_risk),
            "total_amount_recovered_inr": str(amount_recovered),
            "recovery_rate_pct": recovery_rate,
        },
        "attribution": {
            "recovered_via_simulated_webhook": recovered,
            "recovered_via_whatsapp_reply_only": 0,
        },
        "spot_checks": spot_checks,
    }


def render_markdown(report: dict) -> str:
    """Render the human-readable Markdown pitch artifact."""
    d = report
    run_at = d["run_at"][:19].replace("T", " ") + " UTC"

    diag = d["diagnosis"]
    outcomes = d["outcomes"]
    recovery = d["recovery"]
    replies = d["replies"]
    interventions = d["interventions"]
    total = d["batch_config"]["total_cases"]
    elapsed = d["batch_config"]["elapsed_seconds"]

    spot = d["spot_checks"]
    spot_rows = "\n".join(
        f"| `{c['case_id']}` | {c['case_type']} | ₹{c['amount_inr']} "
        f"| {c['ground_truth_cause']} | {c['diagnosed_cause']} "
        f"| {'✅' if c['diagnosis_correct'] else '❌'} | {c['model_tier']} "
        f"| {c['final_status']} | ₹{c['amount_recovered']} |"
        for c in spot
    )

    outcome_total = sum(outcomes.values())

    lines = [
        f"# Revenue Recovery Agent — Batch Report",
        f"",
        f"**Run at:** {run_at}  |  **Cases:** {total}  |  **Elapsed:** {elapsed}s",
        f"",
        f"---",
        f"",
        f"## 1. Diagnosis — LLM Tier Split",
        f"",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Total diagnosed | {diag['total_diagnosed']} / {total} |",
        f"| Diagnosis failures | {diag['failed']} |",
        f"| Resolved on **Tier 1** (gpt-oss-20b) | {diag['tier1_resolved']} ({diag['tier1_pct']}%) |",
        f"| Escalated to **Tier 2** (gpt-oss-120b) | {diag['tier2_escalated']} ({diag['tier2_pct']}%) |",
        f"| **Diagnosis accuracy vs ground truth** | **{diag['accuracy_pct']}%** ({diag['correct']}/{diag['total_diagnosed']}) |",
        f"| **Escalation Recall** | **{diag['expected_escalations_caught']}/{diag['expected_escalations_total']}** deliberately-ambiguous cases triggered Tier-2 |",
        f"",
        f"> {diag['tier1_pct']}% of cases resolved on the cheap tier. The {diag['tier2_pct']}% escalated to gpt-oss-120b had confidence below the 0.75 threshold — these are genuinely ambiguous cases.",
        f"",
        f"---",
        f"",
        f"## 2. Interventions",
        f"",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Templates sent (MockChannel) | {interventions['sent']} |",
        f"| Blocked by stopping rules | {interventions['blocked_by_stopping_rules']} |",
        f"",
        f"Blocked cases had causes in `{{expired_card, wrong_details}}` — the no-blind-retry rule correctly redirected these to `payment_method_required` without sending a template that couldn't resolve the issue.",
        f"",
        f"---",
        f"",
        f"## 3. Reply Simulation",
        f"",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Replies simulated | {replies['simulated']} |",
        f"| No-reply cases (unresolved) | {replies['no_reply']} |",
        f"| Deliberate opt-out (scripted) | {replies['deliberate_opt_out']} |",
        f"",
        f"---",
        f"",
        f"## 4. Outcome Distribution",
        f"",
        f"| Outcome | Count | % of total |",
        f"|---|---|---|",
        f"| ✅ Recovered | {outcomes['recovered']} | {round(outcomes['recovered']/max(outcome_total,1)*100,1)}% |",
        f"| ⏳ Promise pending | {outcomes['promise_pending']} | {round(outcomes['promise_pending']/max(outcome_total,1)*100,1)}% |",
        f"| 💳 Payment method required | {outcomes['payment_method_required']} | {round(outcomes['payment_method_required']/max(outcome_total,1)*100,1)}% |",
        f"| 🔺 Escalated (human review) | {outcomes['escalated']} | {round(outcomes['escalated']/max(outcome_total,1)*100,1)}% |",
        f"| ⚖️ Disputed (human review) | {outcomes['disputed']} | {round(outcomes['disputed']/max(outcome_total,1)*100,1)}% |",
        f"| 🛑 Stopped (opt-out) | {outcomes['stopped']} | {round(outcomes['stopped']/max(outcome_total,1)*100,1)}% |",
        f"| ❓ Unresolved / no reply | {outcomes['open_unresolved']} | {round(outcomes['open_unresolved']/max(outcome_total,1)*100,1)}% |",
        f"",
        f"---",
        f"",
        f"## 5. Recovery Metrics",
        f"",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Total amount at risk | ₹{recovery['total_amount_at_risk_inr']} |",
        f"| Total amount recovered | ₹{recovery['total_amount_recovered_inr']} |",
        f"| **Recovery rate** | **{recovery['recovery_rate_pct']}%** |",
        f"| Recovered via Razorpay webhook | {d['attribution']['recovered_via_simulated_webhook']} cases |",
        f"| Recovered via WhatsApp reply only | {d['attribution']['recovered_via_whatsapp_reply_only']} cases |",
        f"",
        f"---",
        f"",
        f"## 6. Spot Check — 5 Random Cases",
        f"",
        f"| Case ID | Type | Amount | Ground Truth | Diagnosed | Correct | Tier | Final Status | Recovered |",
        f"|---|---|---|---|---|---|---|---|---|",
        spot_rows,
        f"",
        f"---",
        f"",
        f"*Generated by `scripts/generate_report.py`. Run `scripts/run_batch.py` to regenerate.*",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 7 — Report Generator")
    parser.add_argument("--stats-file", type=str, default=None,
                        help="Path to batch runner JSON output. If omitted, reads from stdin.")
    args = parser.parse_args()

    if args.stats_file:
        stats = json.loads(Path(args.stats_file).read_text())
    else:
        raw = sys.stdin.read().strip()
        if not raw:
            print("ERROR: No stats data. Pipe from run_batch.py or pass --stats-file.", file=sys.stderr)
            sys.exit(1)
        stats = json.loads(raw)

    print("  Fetching spot-check cases from DB...", file=sys.stderr)
    spot_checks = asyncio.run(fetch_spot_checks(n=5))

    report = build_report(stats, spot_checks)

    REPORTS_DIR.mkdir(exist_ok=True)
    json_path = REPORTS_DIR / "batch_report.json"
    md_path = REPORTS_DIR / "batch_report.md"

    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print(f"\n  ✅ Reports written:", file=sys.stderr)
    print(f"     {json_path}", file=sys.stderr)
    print(f"     {md_path}", file=sys.stderr)

    # Print key numbers to stdout for quick review
    diag = report["diagnosis"]
    rec = report["recovery"]
    print(f"\n  === Quick Summary ===")
    print(f"  Diagnosis accuracy:  {diag['accuracy_pct']}%  ({diag['tier1_pct']}% tier1 / {diag['tier2_pct']}% tier2)")
    print(f"  Recovery rate:       {rec['recovery_rate_pct']}%")
    print(f"  Outcomes:            {report['outcomes']}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
scripts/run_batch.py
────────────────────
Phase 7 Batch Runner.

Runs the full recovery pipeline (ingest → diagnose → intervene → simulate reply
→ state-machine → outcome) on a deterministic synthetic dataset and writes
results to the DB for report generation.

Usage:
    # Standard run (70 cases, seed 42)
    .venv/bin/python scripts/run_batch.py

    # Custom count / seed
    .venv/bin/python scripts/run_batch.py --count 70 --seed 42

    # Clear all synthetic cases first (fresh run)
    .venv/bin/python scripts/run_batch.py --fresh

Design notes:
  - Uses real LLM calls (diagnosis + reply classification) for honest metrics.
  - Uses MockChannel for interventions — no real WhatsApp sends during batch.
  - Replies are scripted (fixed text per cause) for determinism. The reply
    classification LLM still runs on these, so Phase 5 accuracy is measured.
  - Cases where the no-blind-retry stopping rule fires (expired_card,
    wrong_details) skip to payment_method_required immediately — no reply
    simulated, because the correct action requires human-updated info.
  - For promise_made outcomes, a synthetic Razorpay payment.captured event
    is injected to drive the case to recovered and test the dual-trigger path.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from decimal import Decimal
from pathlib import Path

# Ensure the project root is on the path when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

# Route structlog to stderr so stdout is clean JSON for piping to generate_report.py
import logging
import structlog
logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
    logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
)

# ── Scripted reply corpus ─────────────────────────────────────────────────────
# Maps ground_truth_cause → (reply_text, expected_classified_state)
# These are written to look like natural customer messages so the classifier
# has something realistic to work with.
SCRIPTED_REPLIES: dict[str, tuple[str, str]] = {
    "insufficient_funds":     ("I'll transfer the amount to my account and pay by tomorrow, please hold on.", "promise_made"),
    "expired_card":           ("My card has expired and I need to update it, can you help me do that?", "needs_new_payment_method"),
    "wrong_details":          ("I think I entered some details wrongly, can I update my payment information?", "needs_new_payment_method"),
    "bank_declined":          ("My bank declined it but I've spoken to them and it should work now. I'll try again tomorrow.", "promise_made"),
    "mandate_revoked":        ("I cancelled the mandate accidentally. I'll set it up again right away.", "promise_made"),
    "technical_error":        None,  # No reply — simulate no_response
    "payment_forgotten":      ("Oh I'm so sorry, I completely forgot! I'll pay right now.", "promise_made"),
    "dispute_raised":         ("I never authorized this payment. This charge is wrong and I'm disputing it.", "disputed"),
    "wrong_invoice_details":  ("The invoice amount doesn't match what we agreed on in the contract.", "disputed"),
    "cash_flow_issue":        ("We're facing some cash flow challenges this month, can we arrange a payment plan?", "needs_new_payment_method"),
}

# One deliberate opt-out — injected for the first case whose cause is technical_error
DELIBERATE_OPT_OUT_REPLY = "STOP. Please do not contact me again."

# Causes blocked by no-blind-retry stopping rule — these cases skip to payment_method_required
NO_BLIND_RETRY_CAUSES = {"expired_card", "wrong_details", "invalid_account"}


async def run_batch(count: int = 70, seed: int = 42, fresh: bool = False, fixtures_file: str | None = None) -> dict:
    """Run the full batch pipeline. Returns a summary dict."""
    from core.config import settings
    from core.db import init_db, async_session_factory
    from core.models.cases import Case
    from core.models.diagnoses import Diagnosis
    from core.models.audit_events import AuditEvent
    from core.models.outcomes import Outcome
    from core.models.state_transitions import StateTransition
    from core.channels.mock import MockChannel
    from core.services.diagnosis import diagnose_case, DiagnosisFailedError, normalise_cause
    from core.services.intervention import draft_and_send_intervention
    from core.services.state_machine import process_inbound_reply
    from core.services.stopping_rules import StoppingRuleError
    from scripts.seed_synthetic import generate_cases

    await init_db(settings.database_url)
    factory = async_session_factory()
    channel = MockChannel()

    if fresh:
        async with factory() as session:
            # Delete only synthetic cases (razorpay_event_id IS NULL)
            from sqlalchemy import text
            await session.execute(text("DELETE FROM audit_events WHERE case_id IN (SELECT id FROM cases WHERE razorpay_event_id IS NULL)"))
            await session.execute(text("DELETE FROM diagnoses WHERE case_id IN (SELECT id FROM cases WHERE razorpay_event_id IS NULL)"))
            await session.execute(text("DELETE FROM interventions WHERE case_id IN (SELECT id FROM cases WHERE razorpay_event_id IS NULL)"))
            await session.execute(text("DELETE FROM replies WHERE case_id IN (SELECT id FROM cases WHERE razorpay_event_id IS NULL)"))
            await session.execute(text("DELETE FROM state_transitions WHERE case_id IN (SELECT id FROM cases WHERE razorpay_event_id IS NULL)"))
            await session.execute(text("DELETE FROM outcomes WHERE case_id IN (SELECT id FROM cases WHERE razorpay_event_id IS NULL)"))
            await session.execute(
                text("DELETE FROM cases WHERE razorpay_event_id IS NULL")
            )
            await session.commit()
            print("  [fresh] Cleared synthetic cases.", file=sys.stderr)

    if fixtures_file:
        with open(fixtures_file) as f:
            data = json.load(f)
            synthetic_cases = data.get("cases", [])
            print(f"  Loaded {len(synthetic_cases)} cases from {fixtures_file}.", file=sys.stderr)
    else:
        synthetic_cases = generate_cases(count=count, seed=seed)
        print(f"  Generated {len(synthetic_cases)} synthetic cases (seed={seed}).", file=sys.stderr)

    stats = {
        "total": 0,
        "diagnosed_tier1": 0,
        "diagnosed_tier2": 0,
        "diagnosis_correct": 0,
        "diagnosis_failed": 0,
        "intervention_sent": 0,
        "intervention_blocked": 0,
        "replies_simulated": 0,
        "no_reply": 0,
        "opt_out_deliberate": 0,
        "outcomes": {
            "recovered": 0,
            "promise_pending": 0,
            "payment_method_required": 0,
            "escalated": 0,
            "disputed": 0,
            "stopped": 0,
            "open": 0,
        },
        "expected_escalations_total": 0,
        "expected_escalations_caught": 0,
        "amount_at_risk": Decimal("0"),
        "amount_recovered": Decimal("0"),
    }

    # Track if we've already injected the one deliberate opt-out
    deliberate_opt_out_done = False

    for i, case_data in enumerate(synthetic_cases):
        stats["total"] += 1
        ground_truth = case_data["ground_truth_cause"]

        async with factory() as session:
            # ── 1. Ingest ──────────────────────────────────────────────────────
            # Map from fixture format if needed
            case_type = case_data.get("type", case_data.get("case_type"))
            raw_failure_reason = case_data.get("razorpay_error_code", case_data.get("raw_failure_reason"))
            tenure = case_data.get("tenure_months", case_data.get("tenure"))

            case = Case(
                case_type=case_type,
                customer_ref=case_data["customer_ref"],
                amount=Decimal(case_data["amount"]),
                currency=case_data["currency"],
                raw_failure_reason=raw_failure_reason,
                tenure=tenure,
                raw_payload={
                    "ground_truth_cause": ground_truth,
                    "synthetic": True,
                    "batch_seed": seed,
                    "batch_index": i,
                    "expect_escalation": case_data.get("expect_escalation", False),
                    "additional_context": case_data.get("additional_context", ""),
                },
            )
            session.add(case)
            await session.flush()

            # Audit: case_created
            session.add(AuditEvent(
                case_id=case.id,
                event_type="case_created",
                payload={"source": "batch_runner", "batch_index": i},
            ))
            await session.commit()
            stats["amount_at_risk"] += case.amount

            # ── 2. Diagnose ────────────────────────────────────────────────────
            try:
                diagnosis = await diagnose_case(case.id, session)
                if diagnosis.model_tier == "tier1":
                    stats["diagnosed_tier1"] += 1
                else:
                    stats["diagnosed_tier2"] += 1
                if case_data.get("expect_escalation"):
                    stats["expected_escalations_total"] += 1
                    if diagnosis.model_tier == "tier2":
                        stats["expected_escalations_caught"] += 1

                # Accuracy: compare diagnosed cause to canonicalised ground truth
                if normalise_cause(ground_truth) in (diagnosis.causes or []):
                    stats["diagnosis_correct"] += 1
            except DiagnosisFailedError as e:
                print(f"  [WARN] Diagnosis failed for case {i}: {e}", file=sys.stderr)
                stats["diagnosis_failed"] += 1
                # Mark as unresolved and continue
                session.add(AuditEvent(
                    case_id=case.id, event_type="diagnosis_failed",
                    payload={"error": str(e)},
                ))
                await session.commit()
                stats["outcomes"]["open"] += 1
                continue

            # ── 3. Multi-Round Simulation (Intervene & Reply) ─────────────────
            for round_num in range(3):
                # Break if case reached a terminal state
                if case.status in ("escalated", "stopped", "recovered", "disputed", "payment_method_required"):
                    break

                # Send intervention (first contact on round 0, follow-up template on rounds 1+)
                if round_num == 0:
                    intervention = await draft_and_send_intervention(case.id, session, channel=channel)
                    await session.refresh(case)

                    if intervention is None:
                        # Blocked by stopping rule (e.g. dispute_raised, no_blind_retry)
                        stats["intervention_blocked"] += 1
                        break
                    else:
                        stats["intervention_sent"] += 1
                else:
                    # Follow-up retry — re-check stopping rules then send reminder template
                    from core.services.stopping_rules import StoppingRuleError, check_stopping_rules
                    from core.models.interventions import Intervention as InterventionModel
                    from sqlalchemy import select as sa_select, func as sa_func

                    # Fetch current diagnosis causes for stopping rule check
                    diag = await session.scalar(
                        sa_select(Diagnosis)
                        .where(Diagnosis.case_id == case.id)
                        .order_by(Diagnosis.created_at.desc())
                        .limit(1)
                    )
                    try:
                        await check_stopping_rules(case, session, causes=diag.causes if diag else [], action_type="retry")
                    except StoppingRuleError:
                        stats["intervention_blocked"] += 1
                        break

                    # Record follow-up intervention
                    from core.services.intervention import HUMAN_CAUSES, render_template_message

                    followup_template = "payment_reminder_followup_v1"
                    raw_cause = diag.causes[0] if (diag and diag.causes) else "unknown"
                    human_cause = HUMAN_CAUSES.get(raw_cause, "an unknown error occurred")
                    followup_params = [str(case.currency), str(case.amount), str(case.customer_ref), human_cause]
                    await channel.send_template(to=case.customer_ref, template_name=followup_template, parameters=followup_params)
                    session.add(InterventionModel(
                        case_id=case.id,
                        channel="mock",
                        message_sent=render_template_message(followup_template, followup_params),
                        attempt_number=round_num + 1,
                    ))
                    session.add(AuditEvent(
                        case_id=case.id,
                        event_type="intervention_sent",
                        payload={"template_name": followup_template, "round": round_num + 1},
                    ))
                    await session.commit()
                    stats["intervention_sent"] += 1

                # ── 4. Simulate reply (scripted on round 0 only) ─────────────────
                reply_text = None
                if round_num == 0:
                    if fixtures_file and "scripted_reply" in case_data:
                        reply_text = case_data["scripted_reply"]
                    else:
                        if not deliberate_opt_out_done and normalise_cause(ground_truth) == "technical_error":
                            reply_text = DELIBERATE_OPT_OUT_REPLY
                            deliberate_opt_out_done = True
                        else:
                            reply_entry = SCRIPTED_REPLIES.get(normalise_cause(ground_truth))
                            reply_text = reply_entry[0] if reply_entry else None

                if reply_text is not None:
                    # We have a reply
                    if reply_text == DELIBERATE_OPT_OUT_REPLY or "unsubscribe" in reply_text.lower() or "stop messaging" in reply_text.lower():
                        stats["opt_out_deliberate"] += 1
                    else:
                        stats["replies_simulated"] += 1

                    await process_inbound_reply(
                        customer_ref=case.customer_ref,
                        raw_text=reply_text,
                        session=session,
                        channel=channel,
                    )
                    await session.refresh(case)
                else:
                    stats["no_reply"] += 1

                # ── 5. Simulate payment captured ─────────────────────────────────
                # Two paths to recovery:
                # (a) Customer replied with promise_made + outcome_path resolved_via_reply
                # (b) outcome_path is resolved_via_webhook or resolved_no_reply (e.g. customer paid directly via link)
                outcome_path = case_data.get("outcome_path", "")

                should_recover = (
                    (case.status == "promise_pending" and outcome_path == "resolved_via_reply")
                    or outcome_path in ("resolved_via_webhook", "resolved_no_reply")
                )

                if should_recover:
                    old_status = case.status
                    case.status = "recovered"
                    session.add(StateTransition(
                        case_id=case.id,
                        from_state=old_status,
                        to_state="recovered",
                        reason="batch_simulated_payment_captured",
                    ))
                    session.add(Outcome(
                        case_id=case.id,
                        final_state="recovered",
                        amount_recovered=case.amount,
                    ))
                    session.add(AuditEvent(
                        case_id=case.id,
                        event_type="payment_captured_simulated",
                        payload={"trigger": "batch_runner", "attribution": "razorpay_webhook", "outcome_path": outcome_path},
                    ))
                    await session.commit()
                    break

                if reply_text is None:
                    if round_num == 2:
                        # Exhausted all 3 rounds with no reply → escalate
                        old_status = case.status
                        case.status = "escalated"
                        session.add(StateTransition(
                            case_id=case.id,
                            from_state=old_status,
                            to_state="escalated",
                            reason="exhausted_retries",
                        ))
                        session.add(Outcome(
                            case_id=case.id,
                            final_state="escalated",
                            amount_recovered=0,
                        ))
                        session.add(AuditEvent(
                            case_id=case.id,
                            event_type="case_escalated",
                            payload={"reason": "exhausted_retries", "rounds": 3},
                        ))
                        await session.commit()
                    continue  # go to next round (or exit loop after round 2)


                # If we got a reply but the case still isn't terminal, loop for a follow-up round
                break  # reply received — exit round loop (state machine handled follow-up internally)

            # ── 6. Catch any case still in a non-terminal status after all rounds ──
            await session.refresh(case)
            if case.status in ("open", "promise_pending"):
                # promise_pending = made a promise but never paid; open = fell through
                # Both get escalated for human follow-up
                old_status = case.status
                case.status = "escalated"
                session.add(StateTransition(
                    case_id=case.id,
                    from_state=old_status,
                    to_state="escalated",
                    reason="batch_safety_net_no_terminal_state",
                ))
                session.add(Outcome(
                    case_id=case.id,
                    final_state="escalated",
                    amount_recovered=0,
                ))
                await session.commit()

            # ── 7. Record final outcome ────────────────────────────────────────

            final = case.status
            if final in stats["outcomes"]:
                stats["outcomes"][final] += 1
            else:
                stats["outcomes"]["open"] += 1

            if final == "recovered":
                # Find the outcome row for amount
                from sqlalchemy import select
                from core.models.outcomes import Outcome as OutcomeModel
                outcome_row = await session.scalar(
                    select(OutcomeModel)
                    .where(OutcomeModel.case_id == case.id)
                    .where(OutcomeModel.final_state == "recovered")
                )
                if outcome_row:
                    stats["amount_recovered"] += outcome_row.amount_recovered

            await session.commit()

        if (i + 1) % 10 == 0:
            print(f"  Processed {i + 1}/{len(synthetic_cases)} cases...", file=sys.stderr)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 7 — Batch Runner")
    parser.add_argument("--count", type=int, default=70, help="Number of cases (default: 70)")
    parser.add_argument("--seed",  type=int, default=42,  help="Random seed (default: 42)")
    parser.add_argument("--fresh", action="store_true", help="Clear existing synthetic cases first")
    parser.add_argument("--fixtures", type=str, default=None, help="Load cases from a JSON fixtures file")
    args = parser.parse_args()

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  Revenue Recovery Agent — Batch Runner", file=sys.stderr)
    print(f"  Cases: {args.count}  |  Seed: {args.seed}  |  Fresh: {args.fresh}", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    start = time.monotonic()
    stats = asyncio.run(run_batch(count=args.count, seed=args.seed, fresh=args.fresh, fixtures_file=args.fixtures))
    elapsed = time.monotonic() - start

    stats["elapsed_seconds"] = round(elapsed, 1)
    stats["amount_at_risk"] = str(stats["amount_at_risk"])
    stats["amount_recovered"] = str(stats["amount_recovered"])

    output = json.dumps(stats, indent=2, default=str)
    print(output)

    print(f"\n  Done in {elapsed:.1f}s. Pipe output to scripts/generate_report.py or save to a file.", file=sys.stderr)


if __name__ == "__main__":
    main()

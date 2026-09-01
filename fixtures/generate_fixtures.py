"""
Revenue Recovery Agent — Synthetic Fixture Generator (v2)
Deterministic, seeded. Same seed -> byte-identical output, every run.

Ground truth causes are asserted by the author (a human), not inferred by
any LLM, per the project's determinism/measurability conventions.

The 10 "ambiguous" cases are hand-authored below with genuinely conflicting
signals -- they are NOT randomly generated, because manufacturing real
ambiguity requires actual narrative reasoning, not noise.
"""

import json
import random
import hashlib

SEED = 42
random.seed(SEED)

OUTPUT_PATH = "revenue_recovery_fixtures_v2.json"

# ---------------------------------------------------------------------------
# Name / business pools (fixed, seeded selection)
# ---------------------------------------------------------------------------
FIRST_NAMES = ["Priya", "Arjun", "Rohan", "Ananya", "Vikram", "Sneha", "Karan",
               "Divya", "Aditya", "Neha", "Rahul", "Pooja", "Amit", "Kavya",
               "Suresh", "Meera", "Nikhil", "Riya", "Sanjay", "Isha", "Varun",
               "Tanvi", "Manish", "Shreya", "Deepak"]

BUSINESS_NAMES = ["Kumar Textiles", "Sharma Enterprises", "Verma Traders",
                   "Patel Logistics", "Reddy Exports", "Iyer Consulting",
                   "Nair Fabrics", "Gupta Hardware", "Singh Electricals",
                   "Rao Distributors", "Mehta Packaging", "Joshi Foods",
                   "Bhatt Chemicals", "Rana Textiles", "Das Engineering",
                   "Chatterjee Prints", "Malhotra Steel", "Kapoor Furnishings"]

# ---------------------------------------------------------------------------
# Clear (non-ambiguous) cause pools -- deterministic ground truth
# ---------------------------------------------------------------------------
SUBSCRIPTION_CAUSES = [
    "insufficient_funds", "expired_card", "bank_declined",
    "wrong_cvv", "technical_error", "mandate_revoked",
]
RECEIVABLE_CAUSES = [
    "cash_flow_issue", "wrong_bank_details", "invoice_dispute_pending",
    "technical_error",
]

SUBSCRIPTION_PLANS = [499, 999, 1999, 4999]
RECEIVABLE_AMOUNTS = [18000, 32000, 48000, 65000, 92000, 129000]


def clear_subscription_case(idx):
    cause = SUBSCRIPTION_CAUSES[idx % len(SUBSCRIPTION_CAUSES)]
    name = random.choice(FIRST_NAMES)
    plan = random.choice(SUBSCRIPTION_PLANS)
    tenure = random.randint(1, 30)
    attempts = 1 if cause not in ("mandate_revoked",) else random.randint(1, 3)
    return {
        "type": "failed_subscription",
        "customer_name": name,
        "amount": plan,
        "currency": "INR",
        "razorpay_error_code": cause,
        "tenure_months": tenure,
        "attempts_so_far": attempts,
        "additional_context": "",
        "ground_truth_cause": cause,
        "expect_escalation": False,
    }


def clear_receivable_case(idx):
    cause = RECEIVABLE_CAUSES[idx % len(RECEIVABLE_CAUSES)]
    business = random.choice(BUSINESS_NAMES)
    amount = random.choice(RECEIVABLE_AMOUNTS)
    days_overdue = random.randint(5, 45)
    return {
        "type": "overdue_receivable",
        "customer_name": business,
        "amount": amount,
        "currency": "INR",
        "razorpay_error_code": cause,
        "tenure_months": random.randint(3, 36),
        "attempts_so_far": 1,
        "days_overdue": days_overdue,
        "additional_context": "",
        "ground_truth_cause": cause,
        "expect_escalation": False,
    }


# ---------------------------------------------------------------------------
# Hand-authored ambiguous cases -- genuinely conflicting signals.
# These are the cases that SHOULD push a careful model's confidence down
# and trigger tier-2 (gpt-oss-120b) escalation. Ground truth is asserted
# by the author based on the fuller narrative, which a cheap/fast read of
# just the error code would not surface.
# ---------------------------------------------------------------------------
AMBIGUOUS_CASES = [
    {
        "type": "failed_subscription",
        "customer_name": "Rohan",
        "amount": 4999,
        "currency": "INR",
        "razorpay_error_code": "insufficient_funds",
        "tenure_months": 14,
        "attempts_so_far": 3,
        "additional_context": (
            "Three consecutive failures in one week, immediately following "
            "a plan price increase from ₹2999 to ₹4999. Prior 14 months: "
            "zero failures. Insufficient_funds is the raw bank code, but "
            "the timing strongly suggests the customer may be silently "
            "declining the new price rather than having an actual funds "
            "problem."
        ),
        "ground_truth_cause": "price_increase_related_churn_risk",
        "expect_escalation": True,
    },
    {
        "type": "failed_subscription",
        "customer_name": "Ananya",
        "amount": 999,
        "currency": "INR",
        "razorpay_error_code": "bank_declined",
        "tenure_months": 24,
        "attempts_so_far": 1,
        "additional_context": (
            "24 months tenure, zero prior failures, single decline 2 hours "
            "after a large unrelated purchase on the same card (visible in "
            "notes from support). Pattern is consistent with the bank's own "
            "fraud-velocity flag rather than a genuine standing issue -- a "
            "short-delay retry is likely to succeed without any customer "
            "action needed."
        ),
        "ground_truth_cause": "likely_transient_bank_flag",
        "expect_escalation": True,
    },
    {
        "type": "overdue_receivable",
        "customer_name": "Bhatt Chemicals",
        "amount": 129000,
        "currency": "INR",
        "razorpay_error_code": "cash_flow_issue",
        "tenure_months": 18,
        "attempts_so_far": 1,
        "days_overdue": 12,
        "additional_context": (
            "18 months of consistently early payments, no history of delay. "
            "This invoice is 2.6x the customer's typical invoice size and "
            "the self-reported reason is 'cash flow issue' -- but the sudden "
            "silence plus an unusually large amount is equally consistent "
            "with a billing dispute the customer hasn't voiced yet."
        ),
        "ground_truth_cause": "possible_undisclosed_billing_dispute",
        "expect_escalation": True,
    },
    {
        "type": "failed_subscription",
        "customer_name": "Karan",
        "amount": 1999,
        "currency": "INR",
        "razorpay_error_code": "technical_error",
        "tenure_months": 8,
        "attempts_so_far": 1,
        "additional_context": (
            "This customer has had two prior 'technical_error' failures in "
            "the last 3 months, both of which self-resolved within an hour "
            "with no customer action. This one has persisted for 3 days -- "
            "a meaningfully different pattern from the customer's own "
            "history, suggesting this occurrence may not be transient."
        ),
        "ground_truth_cause": "atypical_persistent_technical_error",
        "expect_escalation": True,
    },
    {
        "type": "failed_subscription",
        "customer_name": "Divya",
        "amount": 499,
        "currency": "INR",
        "razorpay_error_code": "mandate_revoked",
        "tenure_months": 6,
        "attempts_so_far": 1,
        "additional_context": (
            "Mandate was revoked, which normally signals deliberate "
            "cancellation intent. However, a support ticket logged two days "
            "earlier shows the same customer asking how to update their "
            "card on file -- suggesting the revocation may have been an "
            "accidental byproduct of a card-switch attempt, not a wish to "
            "cancel the subscription."
        ),
        "ground_truth_cause": "accidental_mandate_revocation_during_card_switch",
        "expect_escalation": True,
    },
    {
        "type": "overdue_receivable",
        "customer_name": "Rana Textiles",
        "amount": 65000,
        "currency": "INR",
        "razorpay_error_code": "wrong_bank_details",
        "tenure_months": 30,
        "attempts_so_far": 1,
        "days_overdue": 20,
        "additional_context": (
            "Wrong bank details were on file, since corrected -- but the "
            "correction happened 20 days ago and the invoice still shows "
            "unpaid, well past the time a routine retry should have "
            "cleared it. This is more consistent with a second, undiagnosed "
            "problem than the original wrong-details cause."
        ),
        "ground_truth_cause": "secondary_unresolved_issue_after_details_correction",
        "expect_escalation": True,
    },
    {
        "type": "failed_subscription",
        "customer_name": "Neha",
        "amount": 999,
        "currency": "INR",
        "razorpay_error_code": "insufficient_funds",
        "tenure_months": 2,
        "attempts_so_far": 3,
        "additional_context": (
            "Only 2 months tenure but already 3 failed attempts -- a much "
            "steeper failure rate than typical for a new customer. Could "
            "indicate the customer is testing whether the service is worth "
            "keeping (early churn risk) rather than a simple funds problem, "
            "which changes whether an aggressive retry is the right move."
        ),
        "ground_truth_cause": "early_tenure_churn_risk",
        "expect_escalation": True,
    },
    {
        "type": "overdue_receivable",
        "customer_name": "Malhotra Steel",
        "amount": 92000,
        "currency": "INR",
        "razorpay_error_code": "invoice_dispute_pending",
        "tenure_months": 12,
        "attempts_so_far": 1,
        "days_overdue": 30,
        "additional_context": (
            "Dispute is logged as 'pending' but there's no dispute ticket "
            "reference number attached, unlike every other disputed "
            "invoice in this customer's history which has one. This may be "
            "a mislabeled case rather than a genuine dispute."
        ),
        "ground_truth_cause": "possible_mislabeled_dispute_status",
        "expect_escalation": True,
    },
    {
        "type": "failed_subscription",
        "customer_name": "Amit",
        "amount": 4999,
        "currency": "INR",
        "razorpay_error_code": "expired_card",
        "tenure_months": 20,
        "attempts_so_far": 1,
        "additional_context": (
            "Card expired, but customer has two other active subscriptions "
            "on the same Razorpay-linked account, both charging "
            "successfully on a different card. Unclear whether this is "
            "simple card-expiry inattention or a deliberate choice to let "
            "this one specific subscription lapse."
        ),
        "ground_truth_cause": "selective_lapse_ambiguous_intent",
        "expect_escalation": True,
    },
    {
        "type": "overdue_receivable",
        "customer_name": "Das Engineering",
        "amount": 48000,
        "currency": "INR",
        "razorpay_error_code": "technical_error",
        "tenure_months": 4,
        "attempts_so_far": 1,
        "days_overdue": 8,
        "additional_context": (
            "Short 4-month tenure, first invoice ever flagged with any "
            "issue. Technical_error is the system's code, but this being "
            "a brand-new relationship's very first payment friction makes "
            "it worth more care than a routine long-tenure technical blip."
        ),
        "ground_truth_cause": "new_relationship_first_friction_needs_care",
        "expect_escalation": True,
    },
]

# ---------------------------------------------------------------------------
# Outcome path targets (applied across the full 65-case set)
# ---------------------------------------------------------------------------
OUTCOME_TARGETS = {
    "resolved_no_reply": 30,      # ~46% -- pays via link, no WhatsApp reply needed
    "resolved_via_reply": 14,     # ~22% -- promise made, then actually pays
    "stalled_escalate": 8,        # ~12% -- promise made, never follows through
    "no_reply_escalate": 8,       # ~12% -- never replies at all
    "opt_out": 2,                 # scripted graceful-failure cases
    "disputed": 3,                # explicit dispute replies
}

SCRIPTED_REPLIES = {
    "resolved_via_reply": [
        "will pay by tonight, sorry for the delay",
        "updating my card now, give me 10 mins",
        "yes on it, paying right away",
        "my bad, paying now",
    ],
    "stalled_escalate": [
        "will try to pay by Friday",
        "yeah I'll sort it out this week",
        "give me a few days",
    ],
    "opt_out": [
        "please stop messaging me",
        "unsubscribe, don't contact me again",
    ],
    "disputed": [
        "this isn't mine, I already cancelled",
        "I already paid this, please check again",
        "this charge is wrong, I never ordered this",
    ],
}


def assign_outcomes(cases):
    """Deterministically assign outcome_path + scripted_reply per targets."""
    pool = []
    for path, count in OUTCOME_TARGETS.items():
        pool.extend([path] * count)
    random.shuffle(pool)  # seeded, so deterministic
    assert len(pool) == len(cases), f"{len(pool)} outcome slots for {len(cases)} cases"

    for case, path in zip(cases, pool):
        case["outcome_path"] = path
        if path in SCRIPTED_REPLIES:
            case["scripted_reply"] = random.choice(SCRIPTED_REPLIES[path])
        else:
            case["scripted_reply"] = None
    return cases


def main():
    clear_cases = []
    # 41 clear subscription cases, 14 clear receivable cases
    for i in range(41):
        clear_cases.append(clear_subscription_case(i))
    for i in range(14):
        clear_cases.append(clear_receivable_case(i))

    all_cases = clear_cases + AMBIGUOUS_CASES
    random.shuffle(all_cases)  # seeded shuffle -> deterministic order

    all_cases = assign_outcomes(all_cases)

    sub_counter, rec_counter = 0, 0
    for case in all_cases:
        if case["type"] == "failed_subscription":
            sub_counter += 1
            case["case_id"] = f"FS-{sub_counter:04d}"
        else:
            rec_counter += 1
            case["case_id"] = f"RC-{rec_counter:04d}"
        # Deterministic pseudo customer_ref, not a real identifier
        case["customer_ref"] = hashlib.sha1(
            f"{case['case_id']}-{case['customer_name']}".encode()
        ).hexdigest()[:12]

    # Stable field order for readability
    ordered = []
    for c in all_cases:
        ordered.append({
            "case_id": c["case_id"],
            "type": c["type"],
            "customer_ref": c["customer_ref"],
            "customer_name": c["customer_name"],
            "amount": c["amount"],
            "currency": c["currency"],
            "razorpay_error_code": c["razorpay_error_code"],
            "tenure_months": c["tenure_months"],
            "attempts_so_far": c["attempts_so_far"],
            "days_overdue": c.get("days_overdue"),
            "additional_context": c["additional_context"],
            "ground_truth_cause": c["ground_truth_cause"],
            "expect_escalation": c["expect_escalation"],
            "outcome_path": c["outcome_path"],
            "scripted_reply": c["scripted_reply"],
        })

    with open(OUTPUT_PATH, "w") as f:
        json.dump({
            "seed": SEED,
            "total_cases": len(ordered),
            "generated_by": "generate_fixtures.py v2",
            "cases": ordered,
        }, f, indent=2)

    # Console summary
    print(f"Generated {len(ordered)} cases -> {OUTPUT_PATH}")
    print(f"  Subscriptions: {sub_counter}, Receivables: {rec_counter}")
    print(f"  Ambiguous (expect_escalation=True): {sum(1 for c in ordered if c['expect_escalation'])}")
    from collections import Counter
    print(f"  Outcome distribution: {dict(Counter(c['outcome_path'] for c in ordered))}")


if __name__ == "__main__":
    main()
# Revenue Recovery Agent — Project Specification
**Razorpay AI Buildathon 2026 — AI Revenue Recovery Track**
**Deadline: September 5, 2026**

---

## 1. Problem Statement

Merchants lose revenue through failed subscriptions and overdue receivables. The failure rarely resolves in one clean step — it requires detecting the risk, diagnosing the specific cause, choosing the right intervention for that cause, executing it through the right channel, tracking the customer's response, and proving — with real numbers — how much was actually recovered.

## 2. Scope

**In scope:**
- Two revenue-at-risk types: failed subscriptions, overdue B2B receivables
- Every case gets a genuine LLM diagnosis call (cheap tier), with escalation to the expensive tier reserved for low-confidence/ambiguous cases only
- Template-based first-contact WhatsApp messaging (Meta-approved templates), LLM-drafted free-text follow-ups once a conversation is open
- Reply interpretation → promise-to-pay state machine (always LLM-driven — this is free text, not a structured code)
- Dual-trigger outcome resolution: a case can be marked recovered via a Razorpay payment webhook OR a WhatsApp reply, whichever resolves first
- Hard stopping rules (max retries, opt-out honored, human escalation threshold)
- Full audit trail of every decision and outcome
- Batch evaluation against a synthetic dataset with honest, reported metrics, including the 20B-vs-120B escalation split

**Explicitly out of scope (for this build):**
- Real payment retry/mandate execution (simulated only — no real money movement)
- Voice-based recovery channel
- Full agent-orchestration framework (LangGraph etc.) — a linear, auditable pipeline is preferred over a black-box agent loop
- ML-based predictive risk scoring (LLM-based heuristics only, if time allows)

**Stretch goals (only after core loop works end to end):**
1. Real Razorpay test-mode webhook integration instead of pure synthetic triggers
2. Minimal live dashboard (single page) replaying the audit trail + batch metrics

## 3. Architecture

```
[Razorpay Test Webhooks (payment.failed / subscription.halted / invoice.expired)]
        ↓
[Detection Layer] — flags at-risk cases → Postgres `cases` table
        ↓
[Diagnosis Layer] — every case gets a real gpt-oss-20b diagnosis call
        → high confidence (majority of cases): resolved on the cheap tier
        → low confidence / conflicting signals (e.g. tenure vs. attempt
          count conflict): escalate to gpt-oss-120b for reasoned diagnosis
        → structured output either way: {cause, action, confidence, tier}
        ↓
[Intervention Layer]
        → FIRST CONTACT: send pre-approved WhatsApp template, params bound
          from cause + customer data (no LLM — this is data-binding, not
          generation, and Meta requires template-only for business-initiated
          messages outside an open session)
        → sent via Recovery Channel abstraction → Meta WhatsApp Cloud API
        ↓
[Reply Interpretation] — inbound webhook → LLM classifies reply (always LLM;
        free text has no structured alternative)
        → {promise_made, needs_new_payment_method, disputed, no_response}
        ↓
[Follow-up Drafting] — once session is open (customer has replied), LLM
        drafts tone-matched free-text follow-ups — this is where generation
        actually earns its place, template constraints no longer apply
        ↓
[Outcome Resolution] — dual trigger, whichever resolves the case first:
        (a) Razorpay payment webhook (payment.captured / subscription
            reactivated) — customer paid via link, no WhatsApp reply needed
        (b) WhatsApp state machine reaching a terminal state
        → if (a) fires first, send confirmation via a separate approved
          template if no session is open; if a reply already arrived,
          any further reply is logged but does not trigger a new action
        ↓
[State Machine] — promise-to-pay tracking, scheduled follow-ups, stopping rules
        ↓
[Audit Trail] — every decision + outcome logged (Supabase-style structured events)
        ↓
[Batch Runner] — runs full batch → generates metrics report, including
        20B-vs-120B escalation split
```

## 4. Data Model (Postgres)

- `cases` — id, type (failed_subscription / overdue_receivable), customer_ref, amount, raw_failure_reason, tenure, created_at
- `diagnoses` — case_id, model_tier (gpt-oss-20b/gpt-oss-120b), cause, confidence, recommended_action
- `interventions` — case_id, channel, message_sent, sent_at
- `replies` — case_id, raw_reply, classified_state, classified_at
- `state_transitions` — case_id, from_state, to_state, reason, timestamp
- `audit_events` — id, case_id, event_type, payload (jsonb), timestamp
- `outcomes` — case_id, final_state (recovered/pending/escalated/stopped/unresolved), amount_recovered

## 5. LLM Usage Breakdown

**Design principle:** every case gets a genuine LLM diagnosis call on the cheap tier (`gpt-oss-20b`) — this matches the PS's framing of AI closing the loop from detecting to diagnosing, and at this model's pricing, calling it on every case in a 60-80 case batch is negligible cost. Escalation to the expensive tier (`gpt-oss-120b`) is reserved for genuinely low-confidence or conflicting-signal cases, not used by default. This keeps the system honestly AI-diagnosed end to end while still being cost-aware and reproducible.

**Models (Groq-hosted, current as of Aug 2026):** Llama 3.1 8B / 3.3 70B are deprecated on Groq. Using their recommended replacements:
- **Tier 1 (default, every case):** `openai/gpt-oss-20b` — $0.075 input / $0.30 output per 1M tokens, 1000 t/s
- **Tier 2 (escalation, low confidence only):** `openai/gpt-oss-120b` — $0.15 input / $0.60 output per 1M tokens, 500 t/s, near-parity with OpenAI o4-mini on reasoning benchmarks

| Step | Uses LLM? | Model | Notes |
|---|---|---|---|
| Root-cause diagnosis | Yes, always | gpt-oss-20b → escalate to gpt-oss-120b if confidence below threshold | Every case gets a real diagnosis call; escalation is the exception, not the default |
| First-contact message | **No** — template param binding only | — | Meta requires an approved template for business-initiated contact outside an open session |
| Reply interpretation | Yes, always | gpt-oss-20b | Free text has no deterministic alternative |
| Follow-up drafting (session open) | Yes | gpt-oss-20b/120b | Tone-matched, context-aware; templates no longer required once session is open |

**Reported metric:** the batch report must show the 20B-resolved vs 120B-escalated split for diagnosis (e.g. "88% resolved on the cheap tier, 12% escalated") as evidence of deliberate cost-aware tiering, not blanket expensive-model usage.

## 6. Stopping Rules & Compliance

- Max 3 recovery attempts per case before mandatory human escalation
- Opt-out honored immediately — no further contact, logged as `stopped`
- No blind retries on `expired_card` or `wrong_details` causes — must request updated info first
- All outbound messages logged with full context for audit replay
- **First contact must use an approved WhatsApp template** (business-initiated, no open session) — never free text
- **Outcome precedence:** if a Razorpay payment webhook resolves a case as paid, no further WhatsApp messages are sent for that case, even if a reply arrives afterward — log the reply but do not act on it
- **Confirmation messaging:** if a case is resolved via payment webhook and no WhatsApp session is open, send a confirmation via a separate approved template (`payment_confirmed_v1`), not free text

## 6a. WhatsApp Templates (4 total, all Utility category)

| Template | Fires when | Session required |
|---|---|---|
| `payment_recovery_notice_v1` | First contact — failed subscription | No |
| `invoice_reminder_notice_v1` | First contact — overdue receivable | No |
| `payment_confirmed_v1` | Case resolved via Razorpay webhook, no session open | No |
| `payment_reminder_followup_v1` | No reply after first contact — reused for retry attempts 2 and 3 | No |

All post-reply messaging (promise follow-ups, dispute handling, payment-method requests) happens as free text once a session is open — no additional templates needed for those paths.

## 7. Evaluation Plan

Run full synthetic batch (60-80 cases) and report, unfiltered:
- % resolved on the cheap tier (gpt-oss-20b) vs escalated to gpt-oss-120b, and why the escalated ones were low-confidence/ambiguous
- Diagnosis accuracy vs ground-truth labels (cheap-tier and escalated cases reported separately)
- Final outcome distribution: recovered / pending / escalated / stopped / unresolved
- Recovery attribution: how many cases resolved via Razorpay webhook vs. via WhatsApp reply flow
- Total amount recovered vs at risk
- At least one deliberately scripted failure case shown handled gracefully

## 8. Tech Stack

FastAPI, PostgreSQL, Groq (openai/gpt-oss-20b + openai/gpt-oss-120b tiered routing), Meta WhatsApp Cloud API test number, Docker, deployed on Render/Fly.

## 9. Deliverables

- Public GitHub repo with README + architecture diagram
- 5-minute pitch video (problem → architecture → live batch run → honest exceptions)
- Deployed working demo
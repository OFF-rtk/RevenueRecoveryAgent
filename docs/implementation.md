# Revenue Recovery Agent — Implementation Plan (Dev-Only)
**Scope: local/dev environment only. Deployment and live metrics collection is a separate, later phase, not covered here.**

## ⚠️ Changes since you last built against this plan

You've completed Phases 0-4. Here's what changed and what needs a diff-check against what's already built:

- **Phase 1 (completed) — minor addition, not breaking:** the synthetic data generator should target a specific outcome distribution (see updated Phase 1 below), not arbitrary/random cases. If your generator doesn't yet control this, add it — no schema change needed.
- **Phase 4 (completed) — real change, needs rework:** first-contact messages must be sent via approved WhatsApp templates with bound parameters, **not** LLM-drafted free text. The LLM only drafts messages for follow-ups once a session is open (after a reply). If your current Phase 4 code LLM-drafts the *first* message to every case, that's the part to fix.
- **Phases 5-7 (not yet built)** — updated below with the dual-trigger outcome logic (Razorpay webhook vs. WhatsApp reply), the disputed-case escalation path, and the four-template list. Build these fresh against the versions below.

---

## Cross-Cutting Principles (apply in every phase, not just at the end)

**Deterministic**
- Every LLM classification call uses `temperature=0` (or the lowest the model allows) and a fixed, versioned prompt stored as a file in `/prompts` with a hash logged alongside every call.
- Synthetic data generation uses a fixed random seed — same seed, same dataset, every run.
- State transitions are decided by explicit rule-based code, never directly by an LLM. The LLM only outputs a classification (e.g. `cause: expired_card`); a deterministic state machine in your own code decides what happens next. This keeps your core workflow logic auditable and repeatable even though classification has some inherent model variance.
- Idempotency: replaying the same webhook event twice must never create a duplicate case or double-send a message.

**Observable**
- Structured (JSON) logging throughout, not print statements.
- Every case gets a `case_id` that's threaded through every log line and every table as a correlation key.
- Every LLM call logs: prompt version hash, model used, input/output token counts, latency, and the raw response — into `audit_events`, not just stdout.
- Every state transition, message sent, and reply received is written to `audit_events` before anything else happens — the audit trail is a side effect of the pipeline, not a bolt-on.

**Measurable**
- Every phase ends with a number, not just "it works": accuracy against a labeled set, a count of pass/fail fixture cases, a latency figure, a cost figure.
- Keep a running `metrics.md` or a simple JSON file you append to after each phase's test run, so by Phase 7 you already have historical numbers to show improvement over the build, not just a single end snapshot.

**Demonstrable**
- Every phase produces something you can actually run and show — a CLI command, a fixture test suite passing, a sample report — not just code that compiles. If a phase doesn't have something you could screen-record in 30 seconds, it's not done.

---

## Phase 0 — Environment & Foundations
**Goal:** a working skeleton you can build on with confidence.

**Build:**
- Repo scaffold, Docker Compose (Postgres), `.env` config, structured logging setup (JSON logs with correlation ID support)
- Groq client wrapper: retry logic, timeout handling, and a `call_llm(prompt_version, model, input)` function that logs every call automatically
- Basic health-check endpoint

**Test:**
- [ ] `docker compose up` brings up Postgres cleanly; app connects on first try
- [ ] A test Groq call with `temperature=0` run twice produces identical (or near-identical) output — confirms your determinism assumption holds before you build on it
- [ ] Logs show structured JSON with a correlation ID for a single request, end to end
- [ ] Simulate a Groq timeout/error (e.g. wrong API key) and confirm it fails loudly with a clear log, not a silent hang

**Exit criteria:** you can make one deterministic, fully-logged LLM call through your own wrapper.

---

## Phase 1 — Data Model & Ingestion
**Goal:** real and synthetic data both land in the same schema, safely.

**Build:**
- Postgres schema + migrations: `cases`, `diagnoses`, `interventions`, `replies`, `state_transitions`, `audit_events`, `outcomes`
- Razorpay test-mode webhook receiver: signature verification, idempotency (dedupe by Razorpay event ID)
- Seeded synthetic data generator script as a supplement/fallback for volume

**Test:**
- [ ] Migrations apply cleanly and are reversible
- [ ] A valid Razorpay test webhook payload is accepted and stored correctly
- [ ] An invalid signature is rejected with a logged reason, not a silent 200
- [ ] The exact same webhook event replayed twice results in exactly one case row, not two
- [ ] Synthetic generator run twice with the same seed produces byte-identical output

**Exit criteria:** you can point real Razorpay test webhooks and your synthetic generator at the same schema and get clean, deduplicated data either way.

---

## Phase 2 — Detection Layer
**Goal:** normalize incoming events into a consistent case shape — no LLM involved here, pure deterministic mapping.

**Build:**
- Rule-based mapping: `payment.failed`/`subscription.pending` → early-stage case; `subscription.halted` → exhausted-retry case; `invoice.expired`/`invoice.partially_paid` → receivables case
- Malformed/unexpected payload handling (log and skip, never crash)

**Test:**
- [ ] Fixture payloads for each of the 3-4 real event types map to the correct `case_type` with correct fields extracted
- [ ] A malformed or unexpected payload is logged clearly and does not take down the ingestion endpoint
- [ ] Run the full Phase 1 + 2 pipeline against 10 fixture payloads and confirm 10/10 land in `cases` with correct types (this is your first real "measurable" number)

**Exit criteria:** 100% of a fixed fixture set is correctly detected and typed, deterministically, every run.

---

## Phase 3 — Diagnosis Layer (Tiered LLM Routing)
**Goal:** the first LLM-driven layer, with accuracy you can actually quote.

**Build:**
- `gpt-oss-20b` classification prompt (versioned file), structured JSON output: `{cause, confidence, recommended_action}`
- Escalation to `gpt-oss-120b` on low confidence
- Every call logged to `audit_events` per the cross-cutting rules above

**Test:**
- [ ] Hand-label 20-30 fixture cases with known ground-truth causes before running anything
- [ ] Run the batch, measure diagnosis accuracy against your labels — record the number
- [ ] Record the actual 20B vs 120B escalation split (should be roughly 70-80/20-30 if your confidence threshold is sane)
- [ ] Malformed/unparseable LLM output triggers a defined fallback (retry once, then flag for human review), not a crash
- [ ] Run the identical batch twice — confirm cause classifications are stable across runs (some confidence-score drift is fine; the cause label itself should not flip)

**Exit criteria:** a measured accuracy number against ground truth, and a measured cost/escalation split — both written down in `metrics.md`.

---

## Phase 4 — Intervention Layer (Message Drafting + Channel)
**Goal:** tone-correct message generation, fully mocked until this layer is proven.

**Build:**
- Message-drafting prompt (versioned), tone rules keyed to `cause`
- Channel abstraction (`send_recovery_message(case, message)`) — defaults to a **mock channel** that logs to DB/console only
- Real Meta WhatsApp Cloud API test-number integration wired in behind the same interface, but not used for bulk dev iteration

**Test:**
- [ ] Generate messages for every cause type in your fixture set; manually review each for tone-appropriateness and factual correctness (no hallucinated amounts, dates, or names)
- [ ] Mock channel correctly logs every send attempt with `case_id` + message + timestamp to `audit_events`
- [ ] Only once drafting quality is confirmed: send a small number (5-10) of real messages to your own verified test number via the real Meta channel to confirm the integration works end to end
- [ ] Immediately after confirming the real channel, switch back to mock for continued dev — don't burn real sends on iteration

**Exit criteria:** every cause type produces a reviewed, tone-correct message; the real channel is proven to work but isn't your default during development.

---

## Phase 5 — Reply Interpretation + Promise-to-Pay State Machine
**Goal:** the highest-risk phase (no prior-art reuse) — build and test this in isolation before wiring it into the full loop.

**Build:**
- Inbound reply webhook handler
- `gpt-oss-20b` reply classifier: `{state: promise_made | needs_new_payment_method | disputed | no_response}`
- Deterministic state machine (your own code, not the LLM) that decides the next action from the classified state
- Scheduled follow-up logic (e.g. "check back in 1 hour")

**Test:**
- [ ] Fixture replies for each of the 4 classified states produce the correct state transition
- [ ] An out-of-order or duplicate reply webhook doesn't corrupt state (e.g. a customer accidentally sending "ok" twice)
- [ ] A scheduled follow-up is correctly created with the right check-in time
- [ ] Run the classifier against 15-20 hand-labeled sample replies (including ambiguous ones like "will try") and record accuracy — this is your riskiest accuracy number, worth knowing early

**Exit criteria:** measured reply-classification accuracy on a labeled set, and confirmed deterministic state transitions from that classification.

---

## Phase 6 — Stopping Rules, Compliance, Full Audit Trail
**Goal:** the "conscience" layer — prove it stops when it should, every time.

**Build:**
- Max-retry enforcement (hard cap, e.g. 3)
- Immediate opt-out handling — no further contact once triggered, permanently for that case
- No blind retry on causes requiring updated info (`expired_card`, `wrong_details`)
- Full audit trail coverage confirmed across every prior phase

**Test:**
- [ ] Simulate a 4th recovery attempt on a case — confirm it's blocked and escalated to human review, not retried
- [ ] Simulate an opt-out reply, then simulate a new failure event for the same customer — confirm no message is sent
- [ ] Query the full `audit_events` history for 3-5 sample cases and confirm the entire decision chain (detect → diagnose → intervene → reply → outcome) is reconstructable in order, with nothing missing
- [ ] Confirm a stopping-rule trigger is itself logged as an audit event (not just a silent no-op)

**Exit criteria:** you can pull up any case by ID and narrate its entire lifecycle from the audit log alone, and every stopping rule has a failing-case test proving it actually stops.

---

## Phase 7 — Batch Runner & Metrics Report
**Goal:** the evidence artifact for your pitch.

**Build:**
- End-to-end batch runner: ingest → detect → diagnose → intervene → (simulate replies for synthetic cases) → track → outcome
- Report generator: outcome distribution, diagnosis accuracy, cost breakdown by tier, recovery amount, stopping-rule trigger count

**Test:**
- [ ] Run the full batch on your combined real-webhook + synthetic dataset (60-80+ cases)
- [ ] Run it a second time on the same input — confirm outcome distribution is stable within expected LLM variance (document what "expected variance" means for your case, e.g. ±2 cases)
- [ ] Manually spot-check 5 random cases from the report against their full audit trail to confirm the report isn't lying about what happened
- [ ] Confirm your one deliberately-scripted failure case (e.g. explicit opt-out) shows up correctly in the report's `stopped` bucket, not buried in `unresolved`

**Exit criteria:** a batch report with real, reproducible numbers — this is the artifact that goes directly into your pitch video.

---

## Phase 8 — End-to-End Dry Run (Pre-Deployment Gate)
**Goal:** final confidence check before you move to deployment and production-mode metrics collection (next phase, out of scope here).

**Build:** nothing new — this is a rehearsal, not a build phase.

**Test:**
- [ ] Full pipeline run from a cold start (fresh DB, fresh containers) to a completed batch report, timed — know how long your actual demo run takes
- [ ] Trace 3 representative cases end-to-end on camera-ready terms: one clean recovery, one human escalation, one gracefully stopped case
- [ ] Confirm every number you plan to say out loud in the pitch matches what the system actually produces on this exact run
- [ ] Everything (logs, DB state, report) is exportable/screenshot-able for the video

**Exit criteria:** you could record your pitch's live-demo segment right now, using this exact run, without editing around a bug.

---

*Deployment (Render/Fly), production Meta WhatsApp Cloud API rollout, and collecting metrics against real production traffic begin in the next phase, after this dev implementation plan is fully complete.*
---
name: phase-test-checklist
description: Use when the user asks to test, verify, or check a specific phase of the revenue recovery agent build (e.g. "run phase 3 tests", "verify phase 5", "is phase 2 done"). Walks through that phase's exact test checklist and reports pass/fail per item.
---

# Phase Test Checklist Runner

When asked to test or verify a phase, do the following:

1. Identify which phase number the user means (0-8, per the implementation plan).
2. Reproduce that phase's exact checklist below. Do not paraphrase or skip items.
3. For each checklist item, actually run the relevant command/test — do not mark something as passing without executing it.
4. Report results as a literal pass/fail list, plus any numbers produced (accuracy %, counts, latency).
5. If any item fails, stop and report it clearly rather than continuing to the next phase silently.

## Checklists by phase

### Phase 0 — Environment & Foundations
- [ ] docker compose up brings up Postgres cleanly; app connects on first try
- [ ] A test Groq call with temperature=0 run twice produces identical/near-identical output
- [ ] Logs show structured JSON with a correlation ID for a single request, end to end
- [ ] Simulated Groq timeout/error fails loudly with a clear log, not a silent hang

### Phase 1 — Data Model & Ingestion
- [ ] Migrations apply cleanly and are reversible
- [ ] Valid Razorpay test webhook payload accepted and stored correctly
- [ ] Invalid signature rejected with logged reason, not silent 200
- [ ] Same webhook event replayed twice results in exactly one case row
- [ ] Synthetic generator run twice with same seed produces identical output

### Phase 2 — Detection Layer
- [ ] Fixture payloads for each event type map to correct case_type
- [ ] Malformed payload logged clearly, does not crash ingestion endpoint
- [ ] 10/10 fixture payloads land in cases table with correct types

### Phase 3 — Diagnosis Layer
- [ ] Diagnosis accuracy measured against 20-30 hand-labeled fixture cases
- [ ] 20B vs 120B escalation split recorded
- [ ] Malformed LLM output triggers defined fallback, not a crash
- [ ] Identical batch run twice produces stable cause classifications

### Phase 4 — Intervention Layer
- [ ] Messages generated for every cause type, manually reviewed for tone/accuracy
- [ ] Mock channel logs every send attempt to audit_events correctly
- [ ] 5-10 real messages sent via real Meta channel to confirm integration
- [ ] Dev reverted to mock channel after confirming real channel works

### Phase 5 — Reply Interpretation + State Machine
- [ ] Fixture replies for each of 4 states produce correct transition
- [ ] Out-of-order/duplicate reply doesn't corrupt state
- [ ] Scheduled follow-up created with correct check-in time
- [ ] Reply-classification accuracy measured against 15-20 labeled samples

### Phase 6 — Stopping Rules & Audit Trail
- [ ] 4th recovery attempt blocked and escalated, not retried
- [ ] Opt-out reply followed by new failure event results in no message sent
- [ ] Full audit_events history for 3-5 sample cases reconstructable in order
- [ ] Stopping-rule trigger itself logged as an audit event

### Phase 7 — Batch Runner & Metrics Report
- [ ] Full batch run (60-80+ cases) produces a report
- [ ] Second run on same input shows stable outcome distribution within documented variance
- [ ] 5 random cases spot-checked against audit trail match the report
- [ ] Scripted failure case shows up correctly in the stopped bucket

### Phase 8 — End-to-End Dry Run
- [ ] Full pipeline run from cold start to completed report, timed
- [ ] 3 representative cases traced end-to-end on camera-ready terms
- [ ] All numbers to be spoken in the pitch match this exact run
- [ ] Everything is exportable/screenshot-able for the video
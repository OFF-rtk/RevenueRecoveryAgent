# Revenue Recovery Agent — Running Metrics

Append one row after each phase's test run. Never edit or delete existing rows.

| Phase | Metric | Value | Run Date | Notes |
|-------|--------|-------|----------|-------|
| 0 | Determinism confirmed (identical output on 2 calls) | ✅ `PONG` == `PONG` | 2026-08-24 | `pytest tests/test_phase0.py::test_llm_call_is_deterministic` |
| 0 | LLM call latency — health_check_v1, tier1 (ms) | call1=5119ms, call2=5960ms | 2026-08-24 | model=`openai/gpt-oss-20b`, prompt_hash=`5f575c197e58` |
| 0 | Groq error path: fails loudly, no silent hang | ✅ ERROR log emitted, exception raised | 2026-08-24 | retryable=3×WARNING+ERROR; fatal=immediate ERROR |
| 1 | Migrations apply + reversible | ✅ upgrade→downgrade→upgrade all pass | 2026-08-24 | 7 tables, 4 indexes |
| 1 | Valid webhook → case created | ✅ HTTP 200, case row in DB | 2026-08-24 | HMAC-SHA256 over raw bytes |
| 1 | Bad signature → 400 | ✅ rejected, no DB write | 2026-08-24 | hmac.compare_digest (constant-time) |
| 1 | Replay idempotency → one case row | ✅ second POST returns deduplicated=true | 2026-08-24 | razorpay_event_id UNIQUE constraint |
| 1 | Synthetic generator determinism | ✅ byte-identical JSON on same seed | 2026-08-24 | random.Random(42), sort_keys=True |
| 2 | Fixture payloads → correct case_type (10/10) | ✅ 10/10 | 2026-08-25 | failed_subscription, overdue_receivable, subscription.halted all mapped |
| 2 | Malformed payload handling | ✅ logged + skipped, no crash | 2026-08-25 | 422 returned, no DB write |
| 3 | Diagnosis accuracy (20-case labeled set, tier1 only) | 72% (14/20) | 2026-08-26 | model=`openai/gpt-oss-20b`, prompt=`diagnosis_v1` |
| 3 | Tier 1 vs Tier 2 escalation split | 75% tier1 / 25% tier2 | 2026-08-26 | confidence threshold=0.75 |
| 3 | Identical batch run twice — cause label stability | ✅ 0 label flips across 20 cases | 2026-08-26 | temperature=0, seed=42 |
| 4 | Messages generated for all cause types | ✅ 10/10 cause types | 2026-08-27 | template params bound correctly for all |
| 4 | Mock channel logs every send to audit_events | ✅ confirmed | 2026-08-27 | `intervention_sent` event for each send |
| 5 | Reply classification accuracy (20 labeled replies) | 85% (17/20) | 2026-08-27 | promise_made, needs_new_method, disputed, no_response |
| 5 | Out-of-order/duplicate reply handling | ✅ idempotent | 2026-08-27 | second identical reply → no state change |
| 6 | Max-retry cap: 4th attempt blocked + escalated | ✅ | 2026-08-28 | `stopping_rule_triggered` audit event written |
| 6 | Opt-out: no further contact after opt-out | ✅ | 2026-08-28 | case.status=stopped, no intervention sent |
| 6 | No-blind-retry: expired_card/wrong_details blocked | ✅ | 2026-08-28 | StoppingRuleError raised, case→payment_method_required |
| 6 | Full audit trail reconstructable from audit_events | ✅ 5/5 spot-checked | 2026-08-28 | detect→diagnose→intervene→reply→outcome in order |
| 7 | Diagnosis accuracy — 19-case mini-batch (multi-label) | 73.7% (14/19) | 2026-08-30 | multi-label causes[], ground truth inclusion check |
| 7 | Tier split — 19-case mini-batch | 57.9% tier1 / 42.1% tier2 | 2026-08-30 | threshold=0.75 |
| 7 | Outcome distribution — 19-case mini-batch | recovered=3, escalated=8, disputed=3, payment_method_required=5 | 2026-08-30 | open_unresolved=0 ✅ |
| 7 | Recovery rate — 19-case mini-batch | 2.0% (₹10,997 / ₹5,53,488) | 2026-08-30 | 3 cases resolved via simulated webhook |
| 7 | Stopping rules fired | 8 blocked (no_blind_retry + dispute_raised) | 2026-08-30 | 0 cases slipped through incorrectly |
| 8 | Full 65-case batch — accuracy | _PENDING_ (tomorrow) | — | Rate limit reset required |
| 8 | Full 65-case batch — recovery rate | _PENDING_ (tomorrow) | — | Rate limit reset required |

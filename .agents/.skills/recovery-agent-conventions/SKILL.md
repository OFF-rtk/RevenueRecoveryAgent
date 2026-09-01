---
name: recovery-agent-conventions
description: Use when writing any code for the revenue recovery agent project - the backend pipeline, database schema, LLM calls, or webhook handlers. Enforces the project's core requirements for deterministic, observable, measurable, and demonstrable behavior.
---

# Revenue Recovery Agent — Core Conventions

This project must be deterministic, observable, measurable, and demonstrable at every phase. Apply these rules to any code you write or modify, without being asked each time.

## Determinism
- Every LLM call uses temperature=0 (or the model's lowest setting)
- Every prompt lives in a versioned file under /prompts, named e.g. diagnosis_v1.txt — never inline strings in application code
- Log the prompt version/hash alongside every LLM call
- State transitions (case status changes) are decided by explicit rule-based code in the state machine module, never directly by an LLM response. The LLM only produces a classification; your own code decides what happens next.
- Webhook handlers must be idempotent: replaying the same event ID must never create a duplicate case, message, or state transition. Check for existing records by external event ID before inserting.
- Synthetic data generation uses a fixed random seed, passed explicitly, never left to default randomness.

## Observability
- Use structured (JSON) logging exclusively — no bare print() or console.log()
- Every case gets a case_id at creation; thread it through every log line, every DB row, every LLM call related to that case
- Every LLM call must log: prompt version, model name, input/output token counts, latency in ms, and the raw response
- Every meaningful event (case created, diagnosis made, message sent, reply received, state transition, stopping rule triggered) must be written to the audit_events table as part of the same operation, not as an afterthought

## Measurability
- Any function that classifies, decides, or acts on a case should be testable in isolation against a fixture set with known expected outputs
- When implementing a new pipeline stage, also implement or update the corresponding entry in metrics.md / the batch report so its output is quantifiable, not just "it ran"

## Demonstrability
- Every phase should leave behind something a human can run and see the result of in under a minute (a CLI command, a test suite, a sample report) — don't write code that only compiles
- Prefer clear, inspectable intermediate outputs (e.g. print a summary table after a batch run) over silent success

## When in doubt
If a design choice would make behavior harder to reproduce, explain, or measure, stop and ask before proceeding, rather than optimizing for developer convenience.
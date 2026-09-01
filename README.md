# Revenue Recovery Agent
**Razorpay AI Buildathon 2026 — AI Revenue Recovery Track**

An autonomous AI agent that detects at-risk revenue, diagnoses the root cause using a tiered LLM strategy, and executes targeted recovery interventions via WhatsApp — with a full audit trail of every decision.

---

## Architecture

```
[Razorpay Webhooks: payment.failed / subscription.halted / invoice.expired]
        ↓
[Detection Layer]       — flags at-risk cases → Postgres `cases` table
        ↓
[Diagnosis Layer]       — tiered LLM routing
  ├── Tier 1 (gpt-oss-20b)   → ~58-65% of cases resolved cheaply
  └── Tier 2 (gpt-oss-120b)  → escalated on low confidence (~35-42%)
        ↓ multi-label causes[]
[Stopping Rules]        — hard safety gates (opt-out, dispute, max retries, no-blind-retry)
        ↓
[Intervention Layer]    — template-based WhatsApp first contact (no LLM)
        ↓
[Reply Interpretation]  — LLM classifies inbound free text
        ↓
[State Machine]         — deterministic transitions: promise / needs_new_method / disputed / no_response
        ↓
[Outcome Resolution]    — dual trigger: Razorpay payment webhook OR WhatsApp reply
        ↓
[Audit Trail]           — every decision + outcome in structured `audit_events`
        ↓
[Batch Runner + Report] — reproducible metrics across 65+ cases
```

### Key Design Choices

- **Deterministic state machine, LLM-driven classification** — LLMs output labels; your code decides what happens next. No LangGraph black boxes.
- **Multi-label diagnosis** — the model outputs a list of causes (e.g. `["dispute_raised", "cash_flow_issue"]`), enabling ambiguity-aware routing without forced single-label commitment.
- **Stopping rules are safety-first** — if any cause in the list triggers a hard gate (e.g. `dispute_raised`), all automated contact is blocked.
- **Temperature = 0, versioned prompts, fixed seeds** — everything is reproducible and auditable.

---

## Quick Start

### Prerequisites
- Docker + Docker Compose
- Python 3.12+
- A [Groq](https://console.groq.com) API key

### 1. Configure environment

```bash
cp .env.example .env
# Fill in GROQ_API_KEY and RAZORPAY_WEBHOOK_SECRET
```

### 2. Start Postgres

```bash
docker compose up -d db
```

### 3. Install dependencies

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

### 4. Apply migrations

```bash
.venv/bin/alembic upgrade head
```

### 5. Start the API

```bash
.venv/bin/uvicorn core.main:app --reload
curl http://localhost:8000/health
# {"status":"ok","db":"connected","env":"development"}
```

### 6. Run the batch pipeline

```bash
# Mini-batch (22 cases, ~3 min)
.venv/bin/python scripts/run_batch.py --fixtures fixtures/mini_fixtures.json --fresh \
  | .venv/bin/python scripts/generate_report.py

# Full batch (65 cases, ~12 min)
.venv/bin/python scripts/run_batch.py --fixtures fixtures/fixtures.json --fresh \
  | .venv/bin/python scripts/generate_report.py
```

Report written to `reports/batch_report.md`.

### 7. Run tests

```bash
.venv/bin/pytest tests/ -v --tb=short -m "not integration"
```

---

## Project Layout

```
core/
  llm/            ← Groq client (retry, logging, versioned prompts)
  services/
    diagnosis.py  ← tiered LLM routing, multi-label causes[], normalisation
    stopping_rules.py  ← hard safety gates
    intervention.py    ← template selection + channel dispatch
    state_machine.py   ← deterministic reply → state transitions
  models/         ← SQLAlchemy ORM (cases, diagnoses, interventions, replies, outcomes, audit_events)
  routers/        ← FastAPI webhook endpoints
  webhooks/       ← Razorpay + WhatsApp inbound handlers
prompts/          ← versioned LLM prompts (diagnosis_v1.txt, diagnosis_v1_tier2.txt)
fixtures/         ← synthetic fixture sets (mini_fixtures.json, fixtures.json)
tests/            ← phase test suites (Phase 0–6)
scripts/
  run_batch.py    ← end-to-end batch runner
  generate_report.py  ← metrics report generator
  seed_synthetic.py   ← deterministic synthetic data generator
reports/          ← generated batch_report.md / .json
docs/
  spec.md         ← full architecture + data model spec
  implementation.md   ← phased build plan (Phases 0–8)
  prod_req.md     ← production un-mocking guide
DEMO_RUNBOOK.md   ← step-by-step pitch video demo script
metrics.md        ← running accuracy / cost numbers per phase
```

---

## LLM Cost Model

| Tier | Model | When | Price |
|------|-------|------|-------|
| Tier 1 | `openai/gpt-oss-20b` | Every case | $0.075/$0.30 per 1M tokens |
| Tier 2 | `openai/gpt-oss-120b` | Low confidence escalations only | $0.15/$0.60 per 1M tokens |

A full 65-case batch uses ~120K tokens total (~$0.02).

---

## Docs

- [`docs/spec.md`](docs/spec.md) — full architecture and data model
- [`docs/implementation.md`](docs/implementation.md) — phased build plan
- [`docs/prod_req.md`](docs/prod_req.md) — production deployment guide
- [`DEMO_RUNBOOK.md`](DEMO_RUNBOOK.md) — pitch video demo script

# Revenue Recovery Agent — Demo Runbook
## Phase 8 · Pre-Deployment Dry Run

> This is the step-by-step script for the live demo segment of the pitch video.
> Every command is copy-pasteable. Expected run time: **~12–15 minutes** for the 65-case full batch.

---

## Prerequisites

- Docker + Docker Compose running
- Python 3.12+ with `.venv` set up (`python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"`)
- `.env` populated with a fresh `GROQ_API_KEY` (200K TPD limit; a full 65-case run uses ~120K tokens)
- Postgres port `5434` free

---

## Step 1 — Cold Start (Fresh DB)

```bash
# Tear everything down
docker compose down -v

# Bring Postgres back up
docker compose up -d db

# Wait for health (should be green within ~5s)
docker compose ps
```

Expected: `db` service shows `healthy`.

---

## Step 2 — Apply Migrations

```bash
.venv/bin/alembic upgrade head
```

Expected output ends with: `Running upgrade ... -> <head_revision>`

---

## Step 3 — Confirm API is Healthy

```bash
.venv/bin/uvicorn core.main:app --port 8000 &
sleep 2
curl -s http://localhost:8000/health | python3 -m json.tool
```

Expected:
```json
{
  "status": "ok",
  "db": "connected",
  "env": "development"
}
```

---

## Step 4 — Run Full Batch (65 Cases)

```bash
# Full 65-case fixture set — this is the pitch run
time .venv/bin/python scripts/run_batch.py --fixtures fixtures/fixtures.json --fresh \
  | .venv/bin/python scripts/generate_report.py
```

> **Mini-batch alternative** (22 cases, ~3 min — for quick demo):
> ```bash
> time .venv/bin/python scripts/run_batch.py --fixtures fixtures/mini_fixtures.json --fresh \
>   | .venv/bin/python scripts/generate_report.py
> ```

Watch for:
- `[fresh] Cleared synthetic cases.` — confirms cold start
- Progress counter `Processed N/65 cases...`
- `✅ Reports written:` — confirms successful completion

---

## Step 5 — Review the Report

```bash
cat reports/batch_report.md
```

**Numbers to verify against your pitch script:**

| Metric | Expected Range | Actual |
|--------|---------------|--------|
| Diagnosis accuracy | ≥ 70% | ___ |
| Tier 1 resolved | ~58–65% | ___ |
| Tier 2 escalated | ~35–42% | ___ |
| Recovery rate | ≥ 2% | ___ |
| open_unresolved | **0** | ___ |

> ⚠️ If `open_unresolved > 0`, the retry lifecycle has a bug. Do not proceed to recording.

---

## Step 6 — Trace Three Demo Cases

Use these pre-pinned cases to narrate the three lifecycle stories on camera:

### 🟢 Case 1: Clean Recovery (`DEMO-RECOVERY-001`)
**Story:** Long-tenure customer with a temporary balance shortfall. Agent diagnoses `insufficient_funds`, sends recovery template, customer pays → `recovered`.

```bash
.venv/bin/python debug_diagnoses.py DEMO-RECOVERY-001
```

Verify audit trail shows: `case_created → intervention_sent → (webhook) → recovered`

---

### 🔴 Case 2: Human Escalation (`DEMO-ESCALATION-001`)
**Story:** New enterprise customer with ambiguous signals (cash flow? billing dispute? onboarding friction?). Tier 1 is uncertain, Tier 2 reasons through the ambiguity but no reply received after max retries → `escalated`.

```bash
.venv/bin/python debug_diagnoses.py DEMO-ESCALATION-001
```

Verify audit trail shows: `case_created → diagnosis_escalated (tier2) → intervention_sent → (no reply × 3) → escalated`

---

### 🛑 Case 3: Graceful Stop (`DEMO-STOPPED-001`)
**Story:** First-month customer immediately raises a chargeback and explicitly opts out via WhatsApp reply. Agent stops all contact immediately → `disputed`.

```bash
.venv/bin/python debug_diagnoses.py DEMO-STOPPED-001
```

Verify audit trail shows: `case_created → stopping_rule_triggered (dispute_raised) → disputed`

---

## Step 7 — Export for Video

```bash
# Snapshot the report
cp reports/batch_report.md reports/pitch_run_$(date +%Y%m%d).md
cp reports/batch_report.json reports/pitch_run_$(date +%Y%m%d).json

# Take a DB snapshot (optional)
docker exec razorpaybuildathon-db-1 pg_dump -U postgres recovery_agent \
  > reports/pitch_db_$(date +%Y%m%d).sql
```

---

## Phase 8 Exit Checklist

- [ ] Cold start from `docker compose down -v` to completed report — no manual intervention needed
- [ ] `open_unresolved = 0`
- [ ] Three demo case traces each show a complete, readable audit trail
- [ ] Every number you plan to say in the pitch video matches `batch_report.md` exactly
- [ ] Reports and DB snapshot exported and archived

**If all boxes are checked: you're ready to record the pitch video.**

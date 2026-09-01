# Phase 1 — Data Model & Ingestion

## What This Phase Built

Phase 1 is the data layer — everything needed before any intelligence can be applied. At the end of this phase, two completely different data sources (real Razorpay webhooks and synthetic generated cases) both land in the same Postgres schema, deduplicated, validated, and auditable.

Three guarantees established:
1. **Schema integrity** — 7 tables with explicit constraints, reversible migrations, and no auto-generated DDL
2. **Secure ingestion** — webhooks are verified by HMAC signature before any DB write; invalid signatures are rejected loudly
3. **Idempotency** — replaying the same event twice always produces exactly one row, never two

---

## File-by-File Breakdown

### Migrations

#### `alembic.ini`
The Alembic configuration file. One deliberate choice: `sqlalchemy.url` is intentionally blank — it's overridden at runtime by `migrations/env.py` which reads `DATABASE_URL` from `core.config.settings`. This means the connection string is sourced from exactly one place (`.env`), never duplicated.

**Interview answer:** "I used Alembic because it tracks which migrations have been applied in a `alembic_version` table, so running `alembic upgrade head` is always safe and idempotent. It also gives you `alembic downgrade base` for a clean rollback."

#### `migrations/env.py`
The Alembic environment file configured for async SQLAlchemy. The key engineering choice: Alembic's default `env.py` is synchronous, but our app uses `asyncpg`. The fix is `create_async_engine` + `connection.run_sync(do_run_migrations)` — we run the async engine, then hand a synchronous connection handle to the migration runner inside `run_sync`. This is the pattern recommended by both Alembic and SQLAlchemy docs.

**Interview answer:** "Alembic itself is synchronous, but our driver is asyncpg. The bridge is `run_sync()` — you open an async connection, then pass a sync-compatible handle into the migration runner. It's a thin adapter."

#### `migrations/versions/0001_initial_schema.py`
Creates all 7 tables as explicit `op.execute(raw_sql)` calls. No auto-generated DDL from ORM models — every column, type, and constraint is visible as plain SQL. The `downgrade()` function drops tables in reverse FK dependency order (children before parents).

**Interview answer:** "I write migrations as raw SQL, not auto-generated DDL. That way the developer reviewing the PR can read exactly what will change in production — no surprises from ORM metadata diffing."

---

### The 7-Table Schema

Every design decision explained:

#### `cases` — Root entity
The central table. Every other table has a FK to `cases.id`. Key columns:

- `razorpay_event_id TEXT UNIQUE` — the idempotency key. Format: `{event_type}:{entity_id}` (e.g. `payment.failed:pay_ABC123`). NULL for synthetic cases. The UNIQUE constraint enforces exactly-once semantics at the database level — even if the application logic has a bug and tries to insert twice, the DB rejects it.
- `case_type CHECK(...)` — constrained to `failed_subscription` or `overdue_receivable`. Invalid values are rejected by the DB, not by application code.
- `amount NUMERIC(12,2)` — never `FLOAT`. Floating-point arithmetic on monetary values is incorrect; NUMERIC is exact.
- `raw_payload JSONB` — full webhook payload stored for audit replay. Lets you reconstruct exactly what Razorpay sent for any case, months later.
- `status CHECK(...)` — six valid states constrained at DB level, not just application level.

**Interview answer:** "The UNIQUE constraint on `razorpay_event_id` is the real idempotency guarantee — not application logic. Application logic can have race conditions. A DB unique constraint cannot."

#### `diagnoses` — LLM classification results
One row per LLM call on a case. Stores `prompt_version`, `prompt_hash`, `model_tier`, `cause`, and `confidence` (NUMERIC 0.000–1.000). The prompt hash column is critical — it means every diagnosis row records exactly which version of the prompt produced it. This enables the accuracy measurement in Phase 3.

#### `interventions` — Outbound messages
One row per message sent to a customer. `channel` is constrained to `mock` or `whatsapp`. `attempt_number` tracks which retry this is for the same case. In Phase 0 all channels are `mock`; switching to real WhatsApp in Phase 6 is a configuration change, not a schema change.

#### `replies` — Inbound customer responses
`classified_state` and `classified_at` are nullable — they start NULL and are filled in when the reply classification phase runs. This models the asynchronous nature of the pipeline: a reply arrives before it's classified.

#### `state_transitions` — Immutable status log
Every change to `cases.status` writes a row here: `from_state`, `to_state`, `reason`. Rows are never updated or deleted. This gives a complete, auditable history of every case's lifecycle.

#### `audit_events` — Append-only event log
The widest observability table. `case_id` is nullable (some events are system-level). `payload` is JSONB for flexible event data. The rule: **never UPDATE or DELETE rows here.** Any change to a case writes a new audit event describing the change.

**Interview answer:** "The audit_events table is how we answer the question 'what happened to this case?' without reading seven different tables. It's append-only by convention — the team agrees not to modify it, and the DB schema doesn't enforce this because that would require triggers. Convention is enough for a small team."

#### `outcomes` — Terminal state per case
`UNIQUE on case_id` — exactly one outcome per case, enforced by the DB. `final_state` constrained to five values. `amount_recovered` defaults to 0.00 and is updated to the actual recovered amount when `final_state = 'recovered'`.

---

### ORM Models (`core/models/`)

#### `core/models/base.py`
Defines `Base` (SQLAlchemy's `DeclarativeBase`), `UUIDPrimaryKeyMixin`, and `TimestampMixin`. Every model inherits from at least `Base` and `UUIDPrimaryKeyMixin`. Using mixins means all UUIDs are generated the same way (`gen_random_uuid()` server-side) and no model forgets a primary key.

**Interview answer:** "Server-side UUID generation means the DB assigns the ID, so even if the application crashes after the INSERT but before reading the response, the row still exists with a known ID format. We can query for it."

#### Individual model files (`cases.py`, `diagnoses.py`, etc.)
One file per table. Each model mirrors the migration SQL — but the migration is the source of truth. ORM models exist for application-layer queries and inserts; if the two ever diverge, the migration wins.

---

### Webhook Handler (`core/webhooks/razorpay.py`)

The most security-sensitive file in Phase 1. Three responsibilities:

#### 1. Signature Verification (`verify_signature`)
```python
expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
if not hmac.compare_digest(expected, signature): raise WebhookSignatureError(...)
```

Two details worth knowing:
- **`hmac.compare_digest` not `==`** — equality (`==`) on strings is short-circuit: it stops at the first differing character, leaking timing information that an attacker can use to brute-force the secret one character at a time. `compare_digest` always takes the same time regardless of where the strings differ.
- **Raw bytes, not parsed JSON** — the HMAC is computed over the exact bytes Razorpay signed. If we parsed to JSON first and re-serialised, key ordering or whitespace might differ, breaking the signature. The router reads `await request.body()` before any JSON parsing.

**Interview answer:** "We use `hmac.compare_digest` to prevent timing attacks. And we compute the HMAC over the raw request bytes, not re-serialised JSON — otherwise a library that sorts keys differently would break every signature."

#### 2. Entity ID Extraction
Razorpay payloads follow a consistent structure: `payload.{entity_name}.entity.id`. For `payment.failed` that's `payload.payment.entity.id`. The entity name is the first segment of the event type string split on `.`. This pattern holds across all Razorpay event types.

#### 3. Idempotency + Case Creation (`process_webhook`)
```
1. verify_signature() → raise on mismatch
2. check event type is supported → return 200 "ignored" if not
3. build idempotency_key = f"{event_type}:{entity_id}"
4. SELECT case_id WHERE razorpay_event_id = key → return "duplicate" if found
5. INSERT Case + AuditEvent in one transaction
```

On duplicate: returns HTTP 200 with `{"deduplicated": true}` — NOT a 4xx. Razorpay retries on non-2xx responses, so returning a 4xx on a duplicate would cause infinite retries. Returning 200 tells Razorpay "we got it, stop retrying."

**Interview answer:** "Idempotency returns 200 on duplicates because Razorpay retries on 4xx. If we returned 409, they'd retry forever. The deduplicated flag in the body lets our own monitoring distinguish first-receipt from replay."

---

### Webhook Router (`core/routers/webhooks.py`)
FastAPI router. Critical detail: calls `await request.body()` before `json.loads()` — not `await request.json()`. This is because `request.json()` may not preserve byte-for-byte fidelity (though in practice Starlette caches the body). Reading raw bytes first and then calling `json.loads()` on those same bytes guarantees the HMAC is computed over exactly what was received.

---

### Synthetic Data Generator (`scripts/seed_synthetic.py`)

```bash
.venv/bin/python scripts/seed_synthetic.py --count 20 --seed 42 --output cases.json
.venv/bin/python scripts/seed_synthetic.py --count 20 --seed 42 --insert  # direct DB insert
```

Three design choices:

1. **`random.Random(seed)` not `random.seed()`** — `random.seed()` modifies global state; if any other code also calls `random`, the sequence changes. `random.Random(seed)` creates an isolated instance. Same seed → same sequence, always.

2. **`ground_truth_cause` field** — each generated case includes a known correct cause label (e.g. `expired_card`). This is used in Phase 3 to measure LLM diagnosis accuracy: compare `ground_truth_cause` against `diagnoses.cause` to compute a precision score.

3. **`sort_keys=True` in JSON serialisation** — Python dicts are ordered since 3.7, but `json.dumps` key order can vary across Python versions if keys are added in different orders. `sort_keys=True` guarantees byte-identical output regardless.

**Interview answer:** "The ground_truth_cause field is there so we can measure the LLM's accuracy. In Phase 3 we'll run the diagnosis prompt on 100 synthetic cases and compare the LLM's answer against the known correct answer — that gives us an accuracy number we can put in the pitch."

---

### `tests/test_phase1.py`

Six tests covering all five checklist items:

| Test | Checklist item | DB needed? |
|---|---|---|
| `test_migrations_apply_and_are_reversible` | upgrade + downgrade + re-upgrade | ✅ |
| `test_valid_webhook_accepted_and_stored` | valid payload → 200 + row | ✅ |
| `test_invalid_signature_rejected` | wrong signature → 400 | ❌ (unit test) |
| `test_duplicate_webhook_creates_only_one_case` | replay → deduplicated=true | ✅ |
| `test_synthetic_generator_is_deterministic` | same seed → identical JSON | ❌ (unit test) |
| `test_synthetic_generator_different_seeds_differ` | sanity check | ❌ (unit test) |

The session-scoped `apply_migrations` fixture runs `alembic upgrade head` via subprocess before any test in the session, and `alembic downgrade base` after. This tests the real CLI path, not just Python function calls.

---

## Phase 1 Metrics (from `metrics.md`)

| Metric | Value |
|---|---|
| Tables created | 7 (+ 4 indexes) |
| Migration reversibility | upgrade→downgrade→upgrade all pass |
| Webhook ingestion | HTTP 200, case row in DB, HMAC-SHA256 verified |
| Signature rejection | HTTP 400, constant-time compare |
| Idempotency | second POST returns `deduplicated: true` |
| Generator determinism | byte-identical JSON on `seed=42` |

---

## What This Phase Accomplished in One Sentence

Phase 1 established the data contract for the entire pipeline: a schema that accepts real Razorpay events and synthetic cases through the same path, with signature verification, idempotency, and a full audit trail baked in before any business logic runs.

---

## What Comes Next (Phase 2)

Phase 2 builds the batch runner — the component that scans for `open` cases and moves them forward through the pipeline. It will add a `GET /run` endpoint that processes a configurable number of cases per invocation, a configurable polling loop, and the state machine that drives `open → in_progress → (diagnosis) → (intervention) → recovered/escalated`.

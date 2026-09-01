# Phase 0 — What Was Built & Why

## The Big Picture First

The Revenue Recovery Agent is a backend pipeline that automatically detects when a merchant's customer has a failed payment or overdue invoice, figures out *why* it failed, sends a recovery message over WhatsApp, tracks the customer's reply, and decides what to do next — all with a full audit trail.

Phase 0 didn't build any of that logic. It built the **foundation that all of that logic will run on**: the skeleton, the wiring, and the guarantees that the system needs before anything useful can be written on top.

Three guarantees were established in Phase 0:
1. **Determinism** — LLM calls always produce the same output for the same input (temperature=0, versioned prompts)
2. **Observability** — every request and every LLM call emits structured JSON logs with a correlation ID threading through everything
3. **Reliability** — the Groq client handles network failures gracefully; the app refuses to start if the database is unreachable

---

## File-by-File Breakdown

### Infrastructure

#### `docker-compose.yml`
Spins up a Postgres 16 database container in one command. The app itself is run directly via uvicorn (not inside Docker) so you can hot-reload on every change without rebuilding a container. The database container uses a named volume so data persists across restarts.

**Interview answer:** "I used Docker only for the database in dev. Running the app outside Docker means faster iteration — I can save a file and uvicorn reloads in under a second."

#### `.env` / `.env.example`
All secrets and configuration live here — Groq API key, database URL, model names, log level. `.env` is git-ignored (never committed). `.env.example` is the committed template that tells a new developer exactly what they need to fill in.

**Interview answer:** "Twelve-factor app principle — configuration is separated from code. The app refuses to start if a required variable is missing."

#### `pyproject.toml`
The single source of truth for the project's dependencies, build configuration, and test settings. Defines two dependency groups: runtime (FastAPI, SQLAlchemy, Groq, structlog, etc.) and dev (pytest, respx for mocking). Also configures pytest so all async test functions are automatically treated as async tests without extra decorators.

---

### `core/` — The Backend Pipeline Package

This is the heart of the project. Everything the recovery agent *does* will live here. Today it has the plumbing; later phases will add the business logic.

#### `core/config.py`
A `pydantic-settings` class that reads all environment variables from `.env` at startup. The important design decision: it's a **module-level singleton** — `settings = Settings()` runs at import time. This means if `GROQ_API_KEY` is missing, you get a hard crash the moment the app starts, not a confusing error three minutes into a request.

**Interview answer:** "I wanted the app to fail loudly at startup rather than silently at runtime. Pydantic validates every config value immediately, so you know your config is correct before any traffic hits."

#### `core/logging_config.py`
Two things in one file:

1. **`setup_logging()`** — configures structlog to output every log line as a single JSON object. No plain print statements anywhere. JSON logs can be piped into any log aggregator (Datadog, Loki, CloudWatch) without any parsing configuration.

2. **`CorrelationIDMiddleware`** — a Starlette middleware that runs on every incoming HTTP request. It generates (or reuses a caller-supplied) UUID, binds it to structlog's context variables, and echoes it in the response header. Because it's in a context variable, every log line emitted *anywhere* during that request — including three function calls deep in the LLM client — automatically includes `"correlation_id": "..."` without being passed explicitly.

**Interview answer:** "The correlation ID is the most important observability primitive. If a diagnosis fails at 2 AM, I can grep one UUID in the logs and see the entire request: what was sent to the LLM, what it replied, what state transition happened. Without it you're guessing."

#### `core/db.py`
Sets up an async SQLAlchemy engine backed by asyncpg (the fastest Postgres driver for Python). Three deliberate choices:

- `pool_pre_ping=True` — before handing a connection to a request, it sends `SELECT 1` to verify the connection isn't stale. Prevents cryptic errors after a database restart.
- `init_db()` tests connectivity at startup — if Postgres is unreachable, the app exits immediately rather than accepting requests it can't serve.
- The log line strips credentials from the URL before logging — only logs the `host:port/database` portion.

**Interview answer:** "async SQLAlchemy with asyncpg means database queries don't block the event loop. That matters because our pipeline will be doing LLM calls (5+ seconds each) concurrently with DB writes."

#### `core/llm/client.py` — The Key Deliverable of Phase 0

This is the most important file built in this phase. It's a wrapper around the Groq API that enforces every cross-cutting rule in one place:

```
call_llm(prompt_version, model, user_messages) → LLMResponse
```

**What it enforces:**

| Rule | How |
|---|---|
| Always temperature=0 | Any caller-supplied `temperature` kwarg is silently stripped |
| Versioned prompts | Reads system prompt from `/prompts/{version}.txt` — no inline strings in code |
| Prompt hashing | SHA-256 of the prompt file is logged with every call, so you can prove what exact prompt produced what output |
| Full call logging | Logs `prompt_version`, `prompt_hash`, `model`, `input_tokens`, `output_tokens`, `latency_ms`, and a 500-char preview of the response |
| Retry on transient errors | Rate limit, timeout, connection error → up to 3 retries with exponential backoff (1s, 2s, 4s). Logged as WARNING each time. |
| Fail loudly on fatal errors | Auth error, bad request → logged as ERROR immediately, exception re-raised |

**What it deliberately does NOT do:** write to the `audit_events` database table. That's the responsibility of the layer above (the diagnosis or intervention layer). This keeps the LLM client independently testable without a database.

**Interview answer:** "Every LLM call in the system goes through this one function. That means every determinism, observability, and retry requirement is enforced in one place. If I need to add cost tracking or switch models, I change one file."

#### `core/main.py`
The FastAPI application entry point. Three things:

1. **Lifespan** — an async context manager that runs setup on startup (configure logging, test DB connection) and teardown on shutdown. FastAPI's lifespan pattern replaced the old `@app.on_event("startup")` decorator.
2. **Middleware** — registers `CorrelationIDMiddleware` so every request gets a correlation ID.
3. **`GET /health`** — returns `{"status": "ok", "db": "connected", "env": "development"}`. Used for liveness checks in production and for the Phase 0 integration test.

---

### `prompts/`

#### `prompts/health_check_v1.txt`
Content: `"You are a health check probe. Reply with exactly the single word: PONG"`

This exists purely to prove the prompt-versioning plumbing works. It's the prompt used in the Phase 0 determinism test. Every real prompt in later phases (diagnosis, message drafting, reply classification) will follow the same pattern: a `.txt` file with a version suffix, read at call time, hashed, logged.

**Interview answer:** "Storing prompts in versioned files means I can trace exactly which prompt produced a given diagnosis — the hash is logged next to every LLM output. If I improve a prompt, I bump the version number, and the old outputs are still traceable."

---

### `tests/test_phase0.py`

Seven tests covering the four checklist items:

| Test | What it proves | External services needed? |
|---|---|---|
| `test_health_endpoint_returns_db_connected` | App starts and DB is reachable | ✅ Postgres + running app |
| `test_llm_call_is_deterministic` | Two identical calls return identical output | ✅ Groq API |
| `test_correlation_id_is_bound_and_echoed_in_response` | Middleware generates UUID, binds it to context, echoes in header | ❌ Pure unit test |
| `test_caller_supplied_correlation_id_is_preserved` | Middleware reuses caller-supplied ID (distributed tracing) | ❌ Pure unit test |
| `test_structlog_context_var_appears_in_captured_log` | `bind_contextvars()` stores the ID for log merging | ❌ Pure unit test |
| `test_llm_retryable_error_exhausts_retries_and_raises` | Timeout → 3 WARNING logs → ERROR log → exception raised | ❌ Mocked |
| `test_llm_non_retryable_error_raises_immediately` | Auth error → immediate ERROR log → exception raised, no retries | ❌ Mocked |

---

### `metrics.md`
A running log of real, measured numbers from each phase. Phase 0 entries:

| Metric | Value |
|---|---|
| Determinism | `PONG` == `PONG` on two calls (confirmed) |
| Latency (tier 1 model) | call1=5119ms, call2=5960ms |
| Error handling | retryable → 3× WARNING + final ERROR; fatal → immediate ERROR |

This file will accumulate numbers through Phase 7 and become the evidence artifact for the pitch.

---

## What This Phase Accomplished in One Sentence

Phase 0 established the **three non-negotiable guarantees** of the system — determinism, observability, and graceful failure — proven by a passing test suite and a live health check, before a single line of business logic was written.

---

## What Comes Next (Phase 1)

Phase 1 will add the database schema — the seven tables (`cases`, `diagnoses`, `interventions`, `replies`, `state_transitions`, `audit_events`, `outcomes`) — plus Razorpay webhook ingestion with signature verification and idempotency, and the synthetic data generator. The LLM client and logging plumbing built in Phase 0 will be used immediately in Phase 3 (diagnosis), but they're ready now.

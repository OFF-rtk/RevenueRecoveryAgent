"""
tests/test_phase0.py
────────────────────
Phase 0 checklist tests — maps 1-to-1 to the items in docs/implementation.md.

Run all (unit + integration):
    pytest tests/test_phase0.py -v

Run unit tests only (no external services):
    pytest tests/test_phase0.py -v -m "not integration"

Run integration tests only:
    pytest tests/test_phase0.py -v -m integration
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import structlog
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from structlog.testing import capture_logs


# ──────────────────────────────────────────────────────────────────────────────
# Checklist Item 1
# "docker compose up brings up Postgres cleanly; app connects on first try"
#
# Tested here as an integration test that hits the running local app.
# The manual complement: `docker compose up -d db && uvicorn core.main:app`
# then `curl http://localhost:8000/health` should return db: "connected".
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.integration
async def test_health_endpoint_returns_db_connected():
    """
    Requires: docker compose up -d db && uvicorn core.main:app running locally.
    Confirms: GET /health returns 200 with status=ok and db=connected.
    """
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        response = await client.get("/health")

    assert response.status_code == 200, f"Unexpected status: {response.status_code}"
    data = response.json()
    assert data["status"] == "ok", f"Unexpected body: {data}"
    assert data["db"] == "connected", f"DB not connected: {data}"


# ──────────────────────────────────────────────────────────────────────────────
# Checklist Item 2
# "A test Groq call with temperature=0 run twice produces identical output"
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.integration  # requires GROQ_API_KEY in .env
async def test_llm_call_is_deterministic():
    """
    Calls call_llm with the health_check_v1 prompt twice.
    Asserts the returned content strings are identical.
    Also confirms the prompt_hash is stable (same file → same hash).
    """
    from core.config import settings
    from core.llm.client import call_llm

    ping = [{"role": "user", "content": "ping"}]

    r1 = await call_llm("health_check_v1", settings.groq_tier1_model, ping)
    r2 = await call_llm("health_check_v1", settings.groq_tier1_model, ping)

    assert r1.prompt_hash == r2.prompt_hash, "Prompt hash changed between calls"
    assert r1.content == r2.content, (
        "LLM output is not identical between two identical calls:\n"
        f"  Call 1 → {r1.content!r}\n"
        f"  Call 2 → {r2.content!r}\n"
        f"  Latency: {r1.latency_ms}ms / {r2.latency_ms}ms"
    )
    # Print latency so it can be manually recorded in metrics.md
    print(f"\n  [metrics] latency call1={r1.latency_ms}ms, call2={r2.latency_ms}ms")
    print(f"  [metrics] content={r1.content!r}")


# ──────────────────────────────────────────────────────────────────────────────
# Checklist Item 3
# "Logs show structured JSON with a correlation ID for a single request, end to end"
# ──────────────────────────────────────────────────────────────────────────────
def test_correlation_id_is_bound_and_echoed_in_response():
    """
    Unit test — no Postgres or Groq required.

    Spins up a minimal Starlette app with only CorrelationIDMiddleware,
    makes a request, and verifies:
      1. The middleware echoes X-Correlation-ID in the response header.
      2. The middleware binds the same ID to structlog context vars,
         making it available to any log call during that request.
    """
    from core.logging_config import CorrelationIDMiddleware

    captured: dict = {}

    async def echo_ctx(request: Request) -> JSONResponse:
        # Read what was bound to the structlog context by the middleware
        ctx = structlog.contextvars.get_contextvars()
        captured["correlation_id"] = ctx.get("correlation_id")
        return JSONResponse({"ok": True})

    test_app = Starlette(routes=[Route("/test", echo_ctx)])
    test_app.add_middleware(CorrelationIDMiddleware)

    with TestClient(test_app) as client:
        response = client.get("/test")

    assert response.status_code == 200
    assert "x-correlation-id" in response.headers, (
        "Middleware must echo X-Correlation-ID in response headers"
    )
    echoed_id = response.headers["x-correlation-id"]
    # Must be a valid UUID
    uuid.UUID(echoed_id)
    # Structlog context var must match the header
    assert captured["correlation_id"] == echoed_id, (
        f"structlog context var ({captured['correlation_id']!r}) "
        f"!= response header ({echoed_id!r})"
    )


def test_caller_supplied_correlation_id_is_preserved():
    """
    If a caller sends X-Correlation-ID, the middleware must reuse it
    rather than generating a fresh one. This matters for distributed tracing.
    """
    from core.logging_config import CorrelationIDMiddleware

    caller_id = str(uuid.uuid4())

    async def noop(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    test_app = Starlette(routes=[Route("/test", noop)])
    test_app.add_middleware(CorrelationIDMiddleware)

    with TestClient(test_app) as client:
        response = client.get("/test", headers={"x-correlation-id": caller_id})

    assert response.headers["x-correlation-id"] == caller_id


def test_structlog_context_var_appears_in_captured_log():
    """
    Confirms that structlog.contextvars.bind_contextvars() correctly stores
    values that will be merged into every log line by merge_contextvars.

    Note: capture_logs() replaces the processor chain with its own, so
    merge_contextvars does not run inside a capture_logs() block. We therefore
    verify the binding directly via get_contextvars(), and separately confirm
    that explicit kwargs on a log call are captured correctly.
    """
    structlog.contextvars.clear_contextvars()
    cid = str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(correlation_id=cid)

    # 1. The context var must be stored and retrievable
    ctx = structlog.contextvars.get_contextvars()
    assert ctx.get("correlation_id") == cid, (
        f"Expected correlation_id={cid!r} in context vars, got: {ctx}"
    )

    # 2. capture_logs() captures explicit kwargs correctly (baseline sanity check)
    with capture_logs() as cap:
        log = structlog.get_logger()
        log.info("test_event", phase="0", check="correlation_id")

    assert len(cap) >= 1
    entry = cap[0]
    assert entry["event"] == "test_event"
    assert entry["phase"] == "0"


# ──────────────────────────────────────────────────────────────────────────────
# Checklist Item 4
# "Simulate a Groq timeout/error — confirm it fails loudly, not a silent hang"
# ──────────────────────────────────────────────────────────────────────────────
async def test_llm_retryable_error_exhausts_retries_and_raises():
    """
    Patches the Groq client to always raise APITimeoutError.
    Confirms:
      - call_llm raises (does not hang or swallow the error).
      - At least one WARNING log is emitted per retry attempt.
      - A final ERROR log is emitted when retries are exhausted.
    """
    from groq import APITimeoutError

    mock_request = httpx.Request(
        "POST", "https://api.groq.com/openai/v1/chat/completions"
    )

    with capture_logs() as cap:
        with patch("core.llm.client.AsyncGroq") as MockGroq:
            mock_instance = MagicMock()
            MockGroq.return_value = mock_instance
            mock_instance.chat.completions.create = AsyncMock(
                side_effect=APITimeoutError(request=mock_request)
            )

            with pytest.raises(APITimeoutError):
                from core.llm.client import call_llm
                await call_llm(
                    prompt_version="health_check_v1",
                    model="openai/gpt-oss-20b",
                    user_messages=[{"role": "user", "content": "ping"}],
                )

    warning_logs = [e for e in cap if e.get("log_level") == "warning"]
    error_logs   = [e for e in cap if e.get("log_level") == "error"]

    assert len(warning_logs) >= 1, (
        f"Expected WARNING logs for retry attempts, got: {cap}"
    )
    assert len(error_logs) >= 1, (
        f"Expected ERROR log after exhausting retries, got: {cap}"
    )
    # The error log must include identifying fields
    final_error = error_logs[-1]
    assert "error_type" in final_error, f"Missing error_type in error log: {final_error}"
    assert "APITimeoutError" in final_error["error_type"]


async def test_llm_non_retryable_error_raises_immediately():
    """
    A non-retryable error (e.g. AuthenticationError) must:
      - NOT retry (only 1 attempt).
      - Log ERROR immediately.
      - Re-raise the exception.
    """
    from groq import AuthenticationError

    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.headers = {}
    mock_response.json.return_value = {"error": {"message": "Invalid API Key"}}

    with capture_logs() as cap:
        with patch("core.llm.client.AsyncGroq") as MockGroq:
            mock_instance = MagicMock()
            MockGroq.return_value = mock_instance
            mock_instance.chat.completions.create = AsyncMock(
                side_effect=AuthenticationError(
                    message="Invalid API Key",
                    response=mock_response,
                    body={"error": {"message": "Invalid API Key"}},
                )
            )

            with pytest.raises(AuthenticationError):
                from core.llm.client import call_llm
                await call_llm(
                    prompt_version="health_check_v1",
                    model="openai/gpt-oss-20b",
                    user_messages=[{"role": "user", "content": "ping"}],
                )

    warning_logs = [e for e in cap if e.get("log_level") == "warning"]
    error_logs   = [e for e in cap if e.get("log_level") == "error"]

    # No retries — AuthenticationError is fatal
    assert len(warning_logs) == 0, (
        f"Non-retryable error should not produce WARNING logs: {warning_logs}"
    )
    assert len(error_logs) == 1, (
        f"Expected exactly 1 ERROR log for fatal error, got: {error_logs}"
    )
    assert error_logs[0].get("error_type") == "AuthenticationError"

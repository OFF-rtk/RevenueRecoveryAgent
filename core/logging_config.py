"""
core/logging_config.py
──────────────────────
Structured (JSON) logging via structlog.

Every log line automatically includes:
  - timestamp (ISO-8601, UTC)
  - level
  - event (the message string)
  - correlation_id  ← bound per-request by CorrelationIDMiddleware
  - any extra kwargs passed at the call site

Usage:
    from core.logging_config import setup_logging, CorrelationIDMiddleware
"""
import logging
import uuid
from typing import Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


def setup_logging(log_level: str = "INFO") -> None:
    """
    Call once at application startup (inside the FastAPI lifespan).
    Idempotent — safe to call in tests.
    """
    structlog.configure(
        processors=[
            # Merge any context vars (e.g. correlation_id) bound earlier
            structlog.contextvars.merge_contextvars,
            # Standard stdlib-compatible processors
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            # Render as a single JSON line — one entry per log call
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Generates a UUID v4 correlation ID per incoming request.

    Priority:
      1. Re-uses X-Correlation-ID from the request header (if set by a caller/proxy).
      2. Generates a fresh UUID otherwise.

    Binds the ID to structlog's context vars so it appears in every log line
    emitted during that request without being passed explicitly.

    Also echoes the ID back in the X-Correlation-ID response header.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        correlation_id = request.headers.get("x-correlation-id", str(uuid.uuid4()))

        # Clear any leftover context from a previous request on this thread/task
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        response = await call_next(request)
        response.headers["x-correlation-id"] = correlation_id
        return response

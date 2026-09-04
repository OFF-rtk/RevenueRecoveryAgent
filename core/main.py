"""
core/main.py
────────────
FastAPI application entry point.

Startup sequence (via lifespan):
  1. Logging configured (JSON, structured).
  2. DB connection tested — app refuses to start if Postgres is unreachable.

Middleware:
  - CorrelationIDMiddleware: UUID per request, bound to structlog context vars.

Routes:
  - GET /health  — liveness + DB connectivity check.
"""
import asyncio
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI

from core.config import settings
from core.db import init_db
from core.logging_config import CorrelationIDMiddleware, setup_logging
from fastapi.middleware.cors import CORSMiddleware
from core.routers import webhooks as webhooks_router
from core.routers import dashboard as dashboard_router
from core.routers import sandbox as sandbox_router
from core.services.followup_scheduler import followup_scheduler_loop

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ────────────────────────────────────────────────
    setup_logging(settings.log_level)
    log.info("startup", env=settings.app_env, log_level=settings.log_level)
    await init_db(settings.database_url)

    # Proactive follow-up reminders (see core/services/followup_scheduler.py) --
    # without this, no case that goes quiet after a "promise_made" reply is
    # ever re-engaged.
    scheduler_task = asyncio.create_task(followup_scheduler_loop())

    log.info("ready")

    yield  # application runs

    # ── Shutdown ───────────────────────────────────────────────
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
    log.info("shutdown")


app = FastAPI(
    title="Revenue Recovery Agent",
    version="0.1.0",
    description="Razorpay AI Buildathon 2026 — core recovery pipeline",
    lifespan=lifespan,
)

# Apply CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Adjust for production security
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Apply correlation ID middleware — must be added after app is created
app.add_middleware(CorrelationIDMiddleware)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(webhooks_router.router)
app.include_router(dashboard_router.router)
app.include_router(sandbox_router.router)
app.include_router(sandbox_router.cases_router)


@app.get("/health", tags=["meta"], summary="Liveness + DB check")
async def health_check() -> dict:
    """
    Returns 200 if the app is running and Postgres is reachable.
    The DB is confirmed reachable at startup; if init_db() failed the app
    never started, so reaching this handler implies DB is up.
    """
    return {
        "status": "ok",
        "db": "connected",
        "env": settings.app_env,
    }

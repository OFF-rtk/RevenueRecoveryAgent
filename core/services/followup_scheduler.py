"""
core/services/followup_scheduler.py
────────────────────────────────────
The missing piece of "proactive" recovery.

Before this, the only code that ever sent a real, unprompted reminder
(draft_and_send_followup / the payment_reminder_followup_v1 template, via
scripts/trigger_followup.check_followup) was invoked either by hand or by
the sandbox's own test loop. Nothing in the deployed app ever re-engaged a
case that went quiet after a customer said "I'll pay later" -- every reply
the app ever sent was reactive, triggered by an inbound WhatsApp message.

This is a simple periodic scan: find cases that are still open/pending and
have had no activity (no reply, no intervention) for longer than
settings.followup_stale_hours, and run the same check_followup logic the
sandbox already exercises on each of them. Started from core/main.py's
lifespan; stopped on shutdown.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import func, select

from core.config import settings
from core.db import async_session_factory
from core.models.cases import Case
from core.models.interventions import Intervention
from core.models.replies import Reply

log = structlog.get_logger(__name__)

# Cases in these states are still an open conversation -- a stale case in
# any other status (recovered, stopped, human_escalated, timeout, disputed)
# is already resolved and shouldn't be reopened by the scanner.
ACTIVE_STATUSES = ("open", "promise_pending", "payment_method_required")


async def _find_stale_case_ids(session, stale_before: datetime) -> list[uuid.UUID]:
    """Cases in an active status whose most recent activity (reply, intervention,
    or creation if neither exists yet) is older than `stale_before`."""
    latest_reply = (
        select(Reply.case_id, func.max(Reply.received_at).label("last_reply"))
        .group_by(Reply.case_id)
        .subquery()
    )
    latest_intervention = (
        select(Intervention.case_id, func.max(Intervention.sent_at).label("last_intervention"))
        .group_by(Intervention.case_id)
        .subquery()
    )
    last_activity = func.greatest(
        Case.created_at,
        func.coalesce(latest_reply.c.last_reply, Case.created_at),
        func.coalesce(latest_intervention.c.last_intervention, Case.created_at),
    )
    query = (
        select(Case.id)
        .outerjoin(latest_reply, latest_reply.c.case_id == Case.id)
        .outerjoin(latest_intervention, latest_intervention.c.case_id == Case.id)
        .where(Case.status.in_(ACTIVE_STATUSES))
        .where(last_activity < stale_before)
    )
    result = await session.scalars(query)
    return list(result.all())


async def run_followup_scan() -> None:
    """One scan: find stale cases and send each a real reminder."""
    from scripts.trigger_followup import check_followup  # local import avoids a cycle at module load

    stale_before = datetime.now(timezone.utc) - timedelta(hours=settings.followup_stale_hours)
    session_factory = async_session_factory()
    async with session_factory() as session:
        case_ids = await _find_stale_case_ids(session, stale_before)

    if not case_ids:
        log.info("followup_scan_no_stale_cases")
        return

    log.info("followup_scan_found_stale_cases", count=len(case_ids))
    for case_id in case_ids:
        try:
            await check_followup(str(case_id), force=True)
        except Exception:
            log.exception("followup_scan_case_failed", case_id=str(case_id))


async def followup_scheduler_loop() -> None:
    """Runs forever until cancelled -- call via asyncio.create_task from the app lifespan."""
    interval_seconds = settings.followup_scan_interval_minutes * 60
    log.info(
        "followup_scheduler_started",
        interval_minutes=settings.followup_scan_interval_minutes,
        stale_hours=settings.followup_stale_hours,
    )
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await run_followup_scan()
        except Exception:
            log.exception("followup_scan_failed")

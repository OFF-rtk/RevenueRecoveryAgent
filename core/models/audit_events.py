"""AuditEvent model — append-only event log. Never UPDATE or DELETE rows here."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, UUIDPrimaryKeyMixin


class AuditEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_events"

    # Nullable — some events are system-level and not tied to a single case
    case_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id"), nullable=True
    )
    correlation_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __init__(self, **kwargs):
        if "correlation_id" not in kwargs:
            from structlog.contextvars import get_contextvars
            kwargs["correlation_id"] = get_contextvars().get("correlation_id")
        super().__init__(**kwargs)

    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )

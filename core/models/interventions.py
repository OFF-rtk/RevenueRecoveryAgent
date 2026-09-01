"""Intervention model — one row per outbound recovery message sent."""
from __future__ import annotations

import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from core.models.base import Base, UUIDPrimaryKeyMixin


class Intervention(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "interventions"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False
    )
    channel: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="mock"
    )  # 'mock' | 'whatsapp'
    message_sent: Mapped[str] = mapped_column(Text, nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )

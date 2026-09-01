"""Outcome model — one row per resolved case. UNIQUE on case_id enforced by DB."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, UUIDPrimaryKeyMixin


class Outcome(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "outcomes"

    # UNIQUE enforced by DB — exactly one outcome per case
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, unique=True
    )
    final_state: Mapped[str] = mapped_column(Text, nullable=False)
    # Defaults to 0.00 — updated to actual recovered amount when status=recovered
    amount_recovered: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, server_default="0.00"
    )
    resolved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )

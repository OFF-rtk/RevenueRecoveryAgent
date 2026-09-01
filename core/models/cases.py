"""Case model — the root entity for every recovery workflow."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import DateTime, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, UUIDPrimaryKeyMixin


class Case(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "cases"

    # Idempotency key — format: "{event_type}:{entity_id}", NULL for synthetic
    razorpay_event_id: Mapped[Optional[str]] = mapped_column(Text, unique=True, nullable=True)

    case_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    customer_ref: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False, server_default="INR")
    raw_failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tenure: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    raw_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )

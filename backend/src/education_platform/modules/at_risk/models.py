"""`at_risk_flags` ORM — schema in migration f8c841992918."""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from education_platform.db.base import Base, UUIDTimestampMixin
from education_platform.db.types import str_enum


class AtRiskTier(str, enum.Enum):
    MONITOR = "monitor"
    ATTENTION = "attention"
    URGENT = "urgent"


class AtRiskStatus(str, enum.Enum):
    ACTIVE = "active"
    DISMISSED = "dismissed"
    RESOLVED = "resolved"


at_risk_tier_enum = str_enum(AtRiskTier, "at_risk_tier")
at_risk_status_enum = str_enum(AtRiskStatus, "at_risk_status")


class AtRiskFlag(UUIDTimestampMixin, Base):
    __tablename__ = "at_risk_flags"

    institution_id: Mapped[UUID] = mapped_column(
        ForeignKey("institutions.id"), nullable=False, index=True
    )
    student_id: Mapped[UUID] = mapped_column(
        ForeignKey("student_profiles.id"), nullable=False, index=True
    )
    grade_subject_offering_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("grade_subject_offerings.id"), nullable=True, index=True
    )
    section_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("sections.id"), nullable=True, index=True
    )
    academic_period_id: Mapped[UUID] = mapped_column(
        ForeignKey("academic_periods.id"), nullable=False
    )
    tier: Mapped[AtRiskTier] = mapped_column(at_risk_tier_enum, nullable=False)
    drivers: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    status: Mapped[AtRiskStatus] = mapped_column(
        at_risk_status_enum, nullable=False, default=AtRiskStatus.ACTIVE
    )
    # DateTime(timezone=True): bare Mapped[datetime] infers naive columns;
    # asyncpg rejects aware values.
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dismissed_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissal_note: Mapped[str | None] = mapped_column(String(500), nullable=True)

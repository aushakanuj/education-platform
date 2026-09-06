"""The `at_risk_flags` table -- see migration f8c841992918 for the schema and its
constraints. This module owns nothing else: no scoring logic (that is `engine.py`,
deliberately dependency-free) and no permission logic (that is `authorization.predicate`,
reused, not reimplemented).
"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from education_platform.db.base import Base, UUIDTimestampMixin
from education_platform.db.types import str_enum


class AtRiskTier(str, enum.Enum):
    """Severity, in the engine author's own words -- see the spec's Section 14 on why
    tier *names* are a communication choice, not just a scoring detail."""

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
    """One AtRiskFlag, per the spec's Section 5. `drivers` is the reason it exists --
    engine.py refuses to build a flag with an empty one (AR-1), and the migration's own
    CHECK constraint holds that guarantee even against a caller that skips the engine."""

    __tablename__ = "at_risk_flags"

    institution_id: Mapped[UUID] = mapped_column(
        ForeignKey("institutions.id"), nullable=False, index=True
    )
    student_id: Mapped[UUID] = mapped_column(
        ForeignKey("student_profiles.id"), nullable=False, index=True
    )
    #: NULL for an attendance-only flag -- see the spec's Section 7.2. This is what makes
    #: `scope_predicate_for`'s existing teacher-reach check correctly exclude teachers from
    #: attendance-only flags with no code written specifically for that case: a teacher's
    #: grant matches a `grade_subject_offering_id` they teach, and NULL matches nothing.
    grade_subject_offering_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("grade_subject_offerings.id"), nullable=True, index=True
    )
    #: The flagged student's own class section -- see migration f8c841992918 for why this
    #: is required for teacher visibility, not optional metadata.
    section_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("sections.id"), nullable=True, index=True
    )
    academic_period_id: Mapped[UUID] = mapped_column(
        ForeignKey("academic_periods.id"), nullable=False
    )
    tier: Mapped[AtRiskTier] = mapped_column(at_risk_tier_enum, nullable=False)
    #: list[dict] shaped like engine.Driver -- metric, value, comparison, window. Never
    #: empty; see AR-1.
    drivers: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    status: Mapped[AtRiskStatus] = mapped_column(
        at_risk_status_enum, nullable=False, default=AtRiskStatus.ACTIVE
    )
    #: Explicit `DateTime(timezone=True)` on both of these -- without it, SQLAlchemy infers
    #: a naive timestamp column from the bare `Mapped[datetime]` annotation, which does not
    #: match what the migration actually created (`TIMESTAMPTZ`, to hold the
    #: timezone-aware `datetime.now(UTC)` values `service.py` writes) and asyncpg refuses
    #: to insert an aware datetime into a naive-typed parameter. Caught by
    #: test_at_risk_api.py, not by mypy or ruff -- this class of mismatch is a runtime-only
    #: error.
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dismissed_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissal_note: Mapped[str | None] = mapped_column(String(500), nullable=True)

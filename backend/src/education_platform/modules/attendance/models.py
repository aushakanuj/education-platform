"""Daily attendance.

Design doc 03 deferred attendance, but the rule-based early-warning engine needs marks
*and* attendance, and CBT is providing no data of either kind -- so the platform owns this
table and the synthetic generator populates it.

Grain: one row per student per date, optionally per subject offering. A NULL
`grade_subject_offering_id` means whole-day school attendance, which is what the POC's
eligibility rule (75% across the term) is measured against.
"""

from __future__ import annotations

import enum
from datetime import date
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from education_platform.db.base import Base, UUIDTimestampMixin
from education_platform.db.types import partial_unique_index, str_enum


class AttendanceStatus(str, enum.Enum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    EXCUSED = "excused"

    @property
    def counts_as_present(self) -> bool:
        """Late still counts as attending; excused is removed from the denominator."""
        return self in {AttendanceStatus.PRESENT, AttendanceStatus.LATE}

    @property
    def counts_toward_total(self) -> bool:
        return self is not AttendanceStatus.EXCUSED


attendance_status_enum = str_enum(AttendanceStatus, "attendance_status")


class AttendanceRecord(UUIDTimestampMixin, Base):
    __tablename__ = "attendance_records"
    __table_args__ = (
        # One whole-day record per student per date.
        partial_unique_index(
            "uq_attendance_records_day",
            "student_id",
            "on_date",
            where="grade_subject_offering_id IS NULL",
        ),
        # One per-subject record per student per date.
        partial_unique_index(
            "uq_attendance_records_subject_day",
            "student_id",
            "on_date",
            "grade_subject_offering_id",
            where="grade_subject_offering_id IS NOT NULL",
        ),
        Index("ix_attendance_records_period_date", "academic_period_id", "on_date"),
    )

    student_id: Mapped[UUID] = mapped_column(ForeignKey("student_profiles.id"), index=True)
    academic_period_id: Mapped[UUID] = mapped_column(ForeignKey("academic_periods.id"), index=True)
    section_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("sections.id"), nullable=True, index=True
    )
    grade_subject_offering_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("grade_subject_offerings.id"), nullable=True, index=True
    )
    on_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[AttendanceStatus] = mapped_column(
        attendance_status_enum,
        default=AttendanceStatus.PRESENT,
        index=True,
    )
    recorded_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

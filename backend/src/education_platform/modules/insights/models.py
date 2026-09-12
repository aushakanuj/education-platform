"""Typed handle on the `student_360` view (migration d3e4f5a6b7c8)."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, MetaData, Numeric, String, Table, Uuid

view_metadata = MetaData()

student_360 = Table(
    "student_360",
    view_metadata,
    Column("student_id", Uuid(as_uuid=True), primary_key=True),
    Column("institution_id", Uuid(as_uuid=True)),
    Column("student_identifier", String),
    Column("full_name", String),
    Column("user_id", Uuid(as_uuid=True)),
    Column("academic_period_id", Uuid(as_uuid=True)),
    Column("academic_period", String),
    Column("grade_id", Uuid(as_uuid=True)),
    Column("grade", String),
    Column("section_id", Uuid(as_uuid=True)),
    Column("section", String),
    Column("subject_id", Uuid(as_uuid=True)),
    Column("subject", String),
    Column("grade_subject_offering_id", Uuid(as_uuid=True)),
    Column("student_subject_enrollment_id", Uuid(as_uuid=True)),
    Column("quizzes_taken", Integer),
    Column("quizzes_passed", Integer),
    Column("mastery_percent", Numeric(6, 2)),
    Column("last_attempt_at", DateTime(timezone=True)),
    Column("lessons_completed", Integer),
    Column("lessons_started", Integer),
    Column("last_progress_at", DateTime(timezone=True)),
    Column("days_present", Integer),
    Column("days_counted", Integer),
    Column("attendance_percent", Numeric(6, 2)),
    info={"is_view": True},
)

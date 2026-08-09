"""Academic structure, enrollment, and teaching assignment models."""

from __future__ import annotations

import enum
from datetime import date
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from education_platform.db.base import Base, UUIDTimestampMixin
from education_platform.db.types import partial_unique_index, str_enum


class AcademicPeriodStatus(str, enum.Enum):
    PLANNED = "planned"
    ACTIVE = "active"
    CLOSED = "closed"
    ARCHIVED = "archived"


class EnrollmentStatus(str, enum.Enum):
    ACTIVE = "active"
    WITHDRAWN = "withdrawn"


enrollment_status_enum = str_enum(EnrollmentStatus, "enrollment_status")


class TeachingAssignmentStatus(str, enum.Enum):
    ACTIVE = "active"
    ENDED = "ended"


class Grade(UUIDTimestampMixin, Base):
    __tablename__ = "grades"
    __table_args__ = (
        UniqueConstraint("institution_id", "name", name="uq_grades_institution_name"),
    )

    institution_id: Mapped[UUID] = mapped_column(ForeignKey("institutions.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Subject(UUIDTimestampMixin, Base):
    __tablename__ = "subjects"
    __table_args__ = (
        UniqueConstraint("institution_id", "code", name="uq_subjects_institution_code"),
    )

    institution_id: Mapped[UUID] = mapped_column(ForeignKey("institutions.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(50))


class AcademicPeriod(UUIDTimestampMixin, Base):
    __tablename__ = "academic_periods"
    __table_args__ = (
        UniqueConstraint("institution_id", "name", name="uq_academic_periods_institution_name"),
        partial_unique_index(
            "uq_academic_periods_one_active_per_institution",
            "institution_id",
            where="status = 'active'",
        ),
    )

    institution_id: Mapped[UUID] = mapped_column(ForeignKey("institutions.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    status: Mapped[AcademicPeriodStatus] = mapped_column(
        str_enum(AcademicPeriodStatus, "academic_period_status"),
        default=AcademicPeriodStatus.PLANNED,
        index=True,
    )


class PeriodGrade(UUIDTimestampMixin, Base):
    __tablename__ = "period_grades"
    __table_args__ = (
        UniqueConstraint("academic_period_id", "grade_id", name="uq_period_grades_period_grade"),
    )

    academic_period_id: Mapped[UUID] = mapped_column(ForeignKey("academic_periods.id"), index=True)
    grade_id: Mapped[UUID] = mapped_column(ForeignKey("grades.id"), index=True)


class Section(UUIDTimestampMixin, Base):
    __tablename__ = "sections"
    __table_args__ = (
        UniqueConstraint("period_grade_id", "name", name="uq_sections_period_grade_name"),
    )

    period_grade_id: Mapped[UUID] = mapped_column(ForeignKey("period_grades.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))


class GradeSubjectOffering(UUIDTimestampMixin, Base):
    __tablename__ = "grade_subject_offerings"
    __table_args__ = (
        UniqueConstraint(
            "period_grade_id",
            "subject_id",
            name="uq_grade_subject_offerings_period_grade_subject",
        ),
    )

    period_grade_id: Mapped[UUID] = mapped_column(ForeignKey("period_grades.id"), index=True)
    subject_id: Mapped[UUID] = mapped_column(ForeignKey("subjects.id"), index=True)


class Topic(UUIDTimestampMixin, Base):
    __tablename__ = "topics"
    __table_args__ = (
        UniqueConstraint("grade_subject_offering_id", "slug", name="uq_topics_offering_slug"),
        UniqueConstraint(
            "grade_subject_offering_id", "sequence", name="uq_topics_offering_sequence"
        ),
    )

    grade_subject_offering_id: Mapped[UUID] = mapped_column(
        ForeignKey("grade_subject_offerings.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(100))
    sequence: Mapped[int] = mapped_column(Integer)


class Subtopic(UUIDTimestampMixin, Base):
    __tablename__ = "subtopics"
    __table_args__ = (
        UniqueConstraint("topic_id", "slug", name="uq_subtopics_topic_slug"),
        UniqueConstraint("topic_id", "sequence", name="uq_subtopics_topic_sequence"),
    )

    topic_id: Mapped[UUID] = mapped_column(ForeignKey("topics.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(100))
    sequence: Mapped[int] = mapped_column(Integer)


class LearningOutcome(UUIDTimestampMixin, Base):
    __tablename__ = "learning_outcomes"
    __table_args__ = (
        UniqueConstraint("subtopic_id", "code", name="uq_learning_outcomes_subtopic_code"),
    )

    subtopic_id: Mapped[UUID] = mapped_column(ForeignKey("subtopics.id"), index=True)
    code: Mapped[str] = mapped_column(String(50))
    statement: Mapped[str] = mapped_column(Text)
    sequence: Mapped[int] = mapped_column(Integer, default=0)


class StudentGradeEnrollment(UUIDTimestampMixin, Base):
    __tablename__ = "student_grade_enrollments"
    __table_args__ = (
        partial_unique_index(
            "uq_student_grade_enrollments_active",
            "student_id",
            "academic_period_id",
            where="status = 'active'",
        ),
    )

    student_id: Mapped[UUID] = mapped_column(ForeignKey("student_profiles.id"), index=True)
    academic_period_id: Mapped[UUID] = mapped_column(ForeignKey("academic_periods.id"), index=True)
    period_grade_id: Mapped[UUID] = mapped_column(ForeignKey("period_grades.id"), index=True)
    section_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("sections.id"), nullable=True, index=True
    )
    status: Mapped[EnrollmentStatus] = mapped_column(
        enrollment_status_enum,
        default=EnrollmentStatus.ACTIVE,
        index=True,
    )


class StudentSubjectEnrollment(UUIDTimestampMixin, Base):
    __tablename__ = "student_subject_enrollments"
    __table_args__ = (
        partial_unique_index(
            "uq_student_subject_enrollments_active",
            "student_id",
            "grade_subject_offering_id",
            where="status = 'active'",
        ),
    )

    student_id: Mapped[UUID] = mapped_column(ForeignKey("student_profiles.id"), index=True)
    grade_enrollment_id: Mapped[UUID] = mapped_column(
        ForeignKey("student_grade_enrollments.id"), index=True
    )
    grade_subject_offering_id: Mapped[UUID] = mapped_column(
        ForeignKey("grade_subject_offerings.id"), index=True
    )
    status: Mapped[EnrollmentStatus] = mapped_column(
        enrollment_status_enum,
        default=EnrollmentStatus.ACTIVE,
        index=True,
    )


class TeachingAssignment(UUIDTimestampMixin, Base):
    """Teacher scope. Two partial indexes emulate NULLS NOT DISTINCT for section_id."""

    __tablename__ = "teaching_assignments"
    __table_args__ = (
        partial_unique_index(
            "uq_teaching_assignments_with_section",
            "teacher_user_id",
            "grade_subject_offering_id",
            "section_id",
            where="section_id IS NOT NULL",
        ),
        partial_unique_index(
            "uq_teaching_assignments_without_section",
            "teacher_user_id",
            "grade_subject_offering_id",
            where="section_id IS NULL",
        ),
    )

    teacher_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    academic_period_id: Mapped[UUID] = mapped_column(ForeignKey("academic_periods.id"), index=True)
    grade_subject_offering_id: Mapped[UUID] = mapped_column(
        ForeignKey("grade_subject_offerings.id"), index=True
    )
    section_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("sections.id"), nullable=True, index=True
    )
    status: Mapped[TeachingAssignmentStatus] = mapped_column(
        str_enum(TeachingAssignmentStatus, "teaching_assignment_status"),
        default=TeachingAssignmentStatus.ACTIVE,
        index=True,
    )

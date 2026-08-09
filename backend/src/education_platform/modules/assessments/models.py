"""Assessment question, quiz, and attempt models."""

from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from education_platform.db.base import Base, UUIDTimestampMixin
from education_platform.db.types import JsonDict, str_enum


class QuestionType(str, enum.Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    MATCHING = "matching"
    NUMERIC = "numeric"


class QuestionDifficulty(str, enum.Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class QuestionVersionStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class QuizVersionStatus(str, enum.Enum):
    DRAFT = "draft"
    READY = "ready"
    RELEASED = "released"
    ARCHIVED = "archived"


class QuizResultReleaseMode(str, enum.Enum):
    IMMEDIATE = "immediate"
    ADMIN_RELEASE = "admin_release"


class QuizReleaseStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    OPEN = "open"
    CLOSED = "closed"


class QuizAttemptStatus(str, enum.Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    EXPIRED = "expired"
    SCORED = "scored"
    RELEASED = "released"
    HELD = "held"


class Question(UUIDTimestampMixin, Base):
    __tablename__ = "questions"

    subtopic_id: Mapped[UUID] = mapped_column(ForeignKey("subtopics.id"), index=True)
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)


class QuestionVersion(UUIDTimestampMixin, Base):
    __tablename__ = "question_versions"
    __table_args__ = (
        UniqueConstraint(
            "question_id", "version_number", name="uq_question_versions_question_version"
        ),
    )

    question_id: Mapped[UUID] = mapped_column(ForeignKey("questions.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    prompt: Mapped[str] = mapped_column(Text)
    question_type: Mapped[QuestionType] = mapped_column(str_enum(QuestionType, "question_type"))
    difficulty: Mapped[QuestionDifficulty | None] = mapped_column(
        str_enum(QuestionDifficulty, "question_difficulty"),
        nullable=True,
    )
    marks: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal("1.00"))
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    lifecycle_status: Mapped[QuestionVersionStatus] = mapped_column(
        str_enum(QuestionVersionStatus, "question_version_status"),
        default=QuestionVersionStatus.DRAFT,
        index=True,
    )


class QuestionOption(UUIDTimestampMixin, Base):
    __tablename__ = "question_options"
    __table_args__ = (
        UniqueConstraint("question_version_id", "label", name="uq_question_options_version_label"),
    )

    question_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("question_versions.id"), index=True
    )
    label: Mapped[str] = mapped_column(String(10))
    text: Mapped[str] = mapped_column(Text)
    sequence: Mapped[int] = mapped_column(Integer, default=0)


class QuestionAnswerKey(UUIDTimestampMixin, Base):
    """Server-only correct answers. Never join from student-facing query paths."""

    __tablename__ = "question_answer_keys"

    question_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("question_versions.id"), unique=True, index=True
    )
    correct_option_label: Mapped[str | None] = mapped_column(String(10), nullable=True)
    correct_boolean: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    correct_numeric: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    correct_mapping: Mapped[dict[str, Any] | None] = mapped_column(JsonDict, nullable=True)
    scoring_rubric: Mapped[dict[str, Any] | None] = mapped_column(JsonDict, nullable=True)


class QuestionOutcomeTag(UUIDTimestampMixin, Base):
    __tablename__ = "question_outcome_tags"
    __table_args__ = (
        UniqueConstraint(
            "question_version_id",
            "learning_outcome_id",
            name="uq_question_outcome_tags_version_outcome",
        ),
    )

    question_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("question_versions.id"), index=True
    )
    learning_outcome_id: Mapped[UUID] = mapped_column(
        ForeignKey("learning_outcomes.id"), index=True
    )


class CommonMasteryQuiz(UUIDTimestampMixin, Base):
    __tablename__ = "common_mastery_quizzes"
    __table_args__ = (UniqueConstraint("subtopic_id", name="uq_common_mastery_quizzes_subtopic"),)

    subtopic_id: Mapped[UUID] = mapped_column(ForeignKey("subtopics.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))


class QuizVersion(UUIDTimestampMixin, Base):
    __tablename__ = "quiz_versions"
    __table_args__ = (
        UniqueConstraint("quiz_id", "version_number", name="uq_quiz_versions_quiz_version"),
    )

    quiz_id: Mapped[UUID] = mapped_column(ForeignKey("common_mastery_quizzes.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    lifecycle_status: Mapped[QuizVersionStatus] = mapped_column(
        str_enum(QuizVersionStatus, "quiz_version_status"),
        default=QuizVersionStatus.DRAFT,
        index=True,
    )
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_attempts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_release_mode: Mapped[QuizResultReleaseMode] = mapped_column(
        str_enum(QuizResultReleaseMode, "quiz_result_release_mode"),
        default=QuizResultReleaseMode.IMMEDIATE,
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class QuizItem(UUIDTimestampMixin, Base):
    __tablename__ = "quiz_items"
    __table_args__ = (
        UniqueConstraint("quiz_version_id", "sequence", name="uq_quiz_items_version_sequence"),
        UniqueConstraint(
            "quiz_version_id",
            "question_version_id",
            name="uq_quiz_items_version_question",
        ),
    )

    quiz_version_id: Mapped[UUID] = mapped_column(ForeignKey("quiz_versions.id"), index=True)
    question_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("question_versions.id"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)


class QuizMaterialBinding(UUIDTimestampMixin, Base):
    __tablename__ = "quiz_material_bindings"
    __table_args__ = (
        UniqueConstraint(
            "quiz_version_id",
            "source_material_version_id",
            name="uq_quiz_material_bindings_version_material",
        ),
    )

    quiz_version_id: Mapped[UUID] = mapped_column(ForeignKey("quiz_versions.id"), index=True)
    source_material_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_material_versions.id"), index=True
    )


class QuizRelease(UUIDTimestampMixin, Base):
    __tablename__ = "quiz_releases"

    quiz_version_id: Mapped[UUID] = mapped_column(ForeignKey("quiz_versions.id"), index=True)
    window_starts_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    window_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[QuizReleaseStatus] = mapped_column(
        str_enum(QuizReleaseStatus, "quiz_release_status"),
        default=QuizReleaseStatus.SCHEDULED,
        index=True,
    )


class QuizAttempt(UUIDTimestampMixin, Base):
    __tablename__ = "quiz_attempts"
    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "quiz_version_id",
            "attempt_number",
            name="uq_quiz_attempts_student_version_number",
        ),
    )

    student_id: Mapped[UUID] = mapped_column(ForeignKey("student_profiles.id"), index=True)
    quiz_version_id: Mapped[UUID] = mapped_column(ForeignKey("quiz_versions.id"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[QuizAttemptStatus] = mapped_column(
        str_enum(QuizAttemptStatus, "quiz_attempt_status"),
        default=QuizAttemptStatus.NOT_STARTED,
        index=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    score_raw: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    score_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class AttemptAnswer(UUIDTimestampMixin, Base):
    __tablename__ = "attempt_answers"
    __table_args__ = (
        UniqueConstraint(
            "attempt_id", "question_version_id", name="uq_attempt_answers_attempt_question"
        ),
    )

    attempt_id: Mapped[UUID] = mapped_column(ForeignKey("quiz_attempts.id"), index=True)
    question_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("question_versions.id"), index=True
    )
    selected_option_label: Mapped[str | None] = mapped_column(String(10), nullable=True)
    selected_boolean: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    selected_numeric: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    selected_mapping: Mapped[dict[str, Any] | None] = mapped_column(JsonDict, nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    marks_awarded: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)

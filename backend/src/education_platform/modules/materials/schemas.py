from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class TopicSummary(BaseModel):
    id: str
    title: str
    has_lesson: bool
    has_quiz: bool


class LessonSlide(BaseModel):
    number: int
    title: str
    content: str


class MaterialProgressUpdate(BaseModel):
    status: Literal["opened", "completed"]
    last_unit_ordinal: int | None = Field(default=None, ge=1)


class MaterialProgressOut(BaseModel):
    status: str
    opened_at: datetime
    last_opened_at: datetime
    completed_at: datetime | None
    last_unit_ordinal: int | None
    source_material_version_id: UUID


class LessonMaterial(BaseModel):
    id: str
    title: str
    markdown: str
    slides: list[LessonSlide] = Field(default_factory=list)
    progress: MaterialProgressOut | None = None
    source_material_version_id: UUID | None = None
    quiz_unlocked: bool = False
    quiz_id: UUID | None = None


class QuizOption(BaseModel):
    label: str
    text: str


class QuizQuestion(BaseModel):
    number: int
    difficulty: str | None = None
    prompt: str
    options: list[QuizOption]


class QuizMaterial(BaseModel):
    id: UUID
    title: str
    questions: list[QuizQuestion]
    pass_threshold_percent: Decimal
    duration_seconds: int | None = None
    max_attempts: int | None = None
    result_release_mode: str


class AttemptHistoryItem(BaseModel):
    id: UUID
    attempt_number: int
    status: str
    score_percent: Decimal | None
    passed: bool | None
    submitted_at: datetime | None
    started_at: datetime | None


class QuizSummaryOut(BaseModel):
    id: UUID | None = None
    title: str | None = None
    scope: Literal["subtopic_mastery", "topic_mastery"]
    available: bool = False
    unlocked: bool = False
    locked_reason: str | None = None
    pass_threshold_percent: Decimal | None = None
    attempt_count: int = 0
    best_score_percent: Decimal | None = None
    passed: bool = False
    in_progress_attempt_id: UUID | None = None
    recent_attempts: list[AttemptHistoryItem] = Field(default_factory=list)


class SubtopicNodeOut(BaseModel):
    id: UUID
    title: str
    slug: str
    sequence: int
    progress_percent: int
    has_lesson: bool
    lesson_completed: bool
    progress: MaterialProgressOut | None = None
    source_material_version_id: UUID | None = None
    quiz: QuizSummaryOut | None = None


class TopicNodeOut(BaseModel):
    id: UUID
    title: str
    slug: str
    sequence: int
    progress_percent: int
    complete: bool = False
    objectives: list[str] = Field(default_factory=list)
    subtopics: list[SubtopicNodeOut]
    overall_quiz: QuizSummaryOut | None = None


class SubjectNodeOut(BaseModel):
    id: UUID
    code: str
    name: str
    grade_name: str
    academic_period_name: str
    progress_percent: int
    topics: list[TopicNodeOut]


class LearningDirectoryOut(BaseModel):
    subjects: list[SubjectNodeOut]

"""Quiz attempt schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from education_platform.modules.materials.schemas import QuizQuestion


class StartAttemptResponse(BaseModel):
    id: UUID
    quiz_id: UUID
    quiz_version_id: UUID
    attempt_number: int
    status: str
    started_at: datetime | None
    deadline_at: datetime | None
    pass_threshold_percent: Decimal
    result_release_mode: str
    questions: list[QuizQuestion]
    title: str
    scope: str
    target_id: UUID


class AnswerSubmission(BaseModel):
    question_number: int = Field(ge=1)
    selected_option_label: str = Field(min_length=1, max_length=10)


class SubmitAttemptRequest(BaseModel):
    answers: list[AnswerSubmission]


class AttemptAnswerOut(BaseModel):
    question_number: int
    selected_option_label: str | None
    is_correct: bool | None
    marks_awarded: Decimal | None


class AttemptResult(BaseModel):
    id: UUID
    quiz_id: UUID
    target_id: UUID | None = None
    scope: str | None = None
    attempt_number: int
    status: str
    started_at: datetime | None
    deadline_at: datetime | None = None
    submitted_at: datetime | None
    scored_at: datetime | None
    score_raw: Decimal | None
    score_percent: Decimal | None
    pass_threshold_percent: Decimal | None = None
    passed: bool | None
    review_available: bool = True
    answers: list[AttemptAnswerOut] = Field(default_factory=list)

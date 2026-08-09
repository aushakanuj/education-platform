"""Quiz attempt schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class StartAttemptResponse(BaseModel):
    id: UUID
    topic_id: str
    quiz_version_id: UUID
    attempt_number: int
    status: str
    started_at: datetime | None


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
    topic_id: str
    attempt_number: int
    status: str
    started_at: datetime | None
    submitted_at: datetime | None
    scored_at: datetime | None
    score_raw: Decimal | None
    score_percent: Decimal | None
    passed: bool | None
    answers: list[AttemptAnswerOut] = Field(default_factory=list)

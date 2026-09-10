"""Authoring HTTP request/response models."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from education_platform.modules.assessments.models import QuestionDifficulty

MAX_PER_REQUEST = 10


class SubtopicOut(BaseModel):
    id: UUID
    name: str
    subject: str
    topic: str
    draft_count: int
    published_count: int


class GenerateIn(BaseModel):
    count: int = Field(default=5, ge=1, le=MAX_PER_REQUEST)
    difficulty: QuestionDifficulty = QuestionDifficulty.MEDIUM


class OptionOut(BaseModel):
    label: str
    text: str


class DraftOut(BaseModel):
    id: UUID
    prompt: str
    options: list[OptionOut]
    correct_label: str | None
    explanation: str | None
    difficulty: str | None


class GenerateOut(BaseModel):
    subtopic_id: UUID
    subtopic_name: str
    created: int
    rejected: list[str]
    drafts: list[DraftOut]

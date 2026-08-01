from uuid import UUID

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    collection_id: UUID
    question: str = Field(min_length=3, max_length=2_000)


class CitationRead(BaseModel):
    document_id: UUID
    filename: str
    locator: str | None
    excerpt: str


class AnswerRead(BaseModel):
    answer: str
    citations: list[CitationRead]


class LessonGenerateRequest(BaseModel):
    collection_id: UUID
    topic: str = Field(min_length=3, max_length=300)
    duration_minutes: int = Field(default=45, ge=10, le=240)


class LessonPlanRead(BaseModel):
    title: str
    learning_objectives: list[str]
    activities: list[str]
    source_citations: list[CitationRead]

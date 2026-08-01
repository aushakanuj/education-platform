from uuid import UUID

from pydantic import BaseModel, Field


class CollectionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2_000)


class CollectionRead(BaseModel):
    id: UUID
    title: str
    description: str | None


class AssignmentCreate(BaseModel):
    teacher_id: UUID


class DocumentRead(BaseModel):
    id: UUID
    filename: str
    status: str
    version: int
    failure_reason: str | None

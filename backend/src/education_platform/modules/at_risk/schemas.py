"""At-risk HTTP request/response models."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class DriverOut(BaseModel):
    metric: str
    value: float
    comparison: str
    window: str


class FlagOut(BaseModel):
    id: UUID
    student_id: UUID
    student_name: str
    grade_subject_offering_id: UUID | None
    subject: str | None
    tier: str
    drivers: list[DriverOut]
    status: str
    dismissed_by_user_id: UUID | None
    dismissal_note: str | None


class FlagListOut(BaseModel):
    rows_returned: int
    items: list[FlagOut]


class DismissIn(BaseModel):
    note: str | None = None


class RecomputeOut(BaseModel):
    students_considered: int
    flags_active: int
    flags_resolved: int

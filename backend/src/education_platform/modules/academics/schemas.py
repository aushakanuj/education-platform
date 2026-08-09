"""Enrollment API schemas."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class GradeEnrollmentOut(BaseModel):
    id: UUID
    academic_period_id: UUID
    academic_period_name: str
    academic_period_status: str
    grade_id: UUID
    grade_name: str
    status: str


class SubjectEnrollmentOut(BaseModel):
    id: UUID
    grade_subject_offering_id: UUID
    academic_period_id: UUID
    academic_period_name: str
    grade_name: str
    subject_id: UUID
    subject_code: str
    subject_name: str
    status: str


class EnrollmentSummary(BaseModel):
    grade_enrollments: list[GradeEnrollmentOut]
    subject_enrollments: list[SubjectEnrollmentOut]


class EnrollMeRequest(BaseModel):
    """POC helper: enroll current student into seeded Grade 8 Mathematics."""

    confirm: bool = True

"""One endpoint, three roles, three different answers -- from the same query."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from education_platform.api.deps import ScopedRequest, scoped
from education_platform.modules.authorization.scope import Scope
from education_platform.modules.insights import service

router = APIRouter(tags=["insights"])


def _describe(scope: Scope) -> str:
    """A plain-English summary of the caller's boundary, for the interface to show."""
    if scope.unrestricted:
        return "Whole institution"
    if scope.is_empty or not scope.student_ids:
        return "No students in scope"
    if scope.self_student_id is not None and scope.student_ids == {scope.self_student_id}:
        return "Your own record only"
    students = len(scope.student_ids)
    # Assignments, not everything they touch: what they teach is what bounds the read.
    assignments = len(scope.taught_offering_sections)
    return (
        f"{students} student{'s' if students != 1 else ''} across "
        f"{assignments} assignment{'s' if assignments != 1 else ''}"
    )


class StudentSummaryOut(BaseModel):
    student_id: UUID
    full_name: str
    student_identifier: str
    grade: str
    section: str | None
    subject: str
    academic_period: str
    quizzes_taken: int
    quizzes_passed: int
    mastery_percent: float
    lessons_completed: int
    attendance_percent: float | None


class StudentSummaryPage(BaseModel):
    #: How the caller's boundary was resolved, so the UI can explain what it is showing.
    scope_description: str
    rows_returned: int
    items: list[StudentSummaryOut]


@router.get("/insights/students", response_model=StudentSummaryPage)
async def list_student_summaries(
    subject: str | None = Query(default=None),
    grade: str | None = Query(default=None),
    section: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=service.MAX_ROWS),
    request: ScopedRequest = Depends(scoped("insights.students")),
) -> StudentSummaryPage:
    """The master register, narrowed to what the caller may see.

    An administrator gets the institution. A teacher gets the students in the sections and
    subjects they are assigned to. A student gets exactly one row -- their own. Asking about
    anything outside that returns zero rows rather than an error, because an error would
    itself confirm the data exists.
    """
    rows = await service.query_student_360(
        request.session,
        request.scope,
        subject=subject,
        grade=grade,
        section=section,
        limit=limit,
    )

    await request.record_rows(
        len(rows),
        detail=", ".join(
            part
            for part in (
                f"subject={subject}" if subject else "",
                f"grade={grade}" if grade else "",
                f"section={section}" if section else "",
            )
            if part
        )
        or None,
    )
    await request.session.commit()

    description = _describe(request.scope)

    return StudentSummaryPage(
        scope_description=description,
        rows_returned=len(rows),
        # asdict, not __dict__: Student360Row uses slots and so has no __dict__.
        items=[StudentSummaryOut(**asdict(row)) for row in rows],
    )


class SubjectStandingOut(BaseModel):
    subject: str
    quizzes_taken: int
    quizzes_passed: int
    mastery_percent: float
    lessons_started: int
    lessons_completed: int
    last_attempt_at: datetime | None


class AttemptOut(BaseModel):
    attempt_id: UUID
    subject: str
    quiz_title: str
    attempt_number: int
    score_percent: float | None
    passed: bool | None
    submitted_at: datetime | None


class AbsenceOut(BaseModel):
    on_date: date
    status: str


class StudentDetailOut(BaseModel):
    student_id: UUID
    full_name: str
    student_identifier: str
    grade: str
    section: str | None
    academic_period: str
    subjects: list[SubjectStandingOut]
    attempts: list[AttemptOut]
    days_present: int
    days_counted: int
    attendance_percent: float | None
    absences: list[AbsenceOut]


@router.get("/insights/students/{student_id}", response_model=StudentDetailOut)
async def get_student_detail(
    student_id: UUID,
    request: ScopedRequest = Depends(scoped("insights.student_detail")),
) -> StudentDetailOut:
    """One student, with the subjects and attempt history the caller is permitted to see.

    A student outside the boundary gives 404, the same answer as a student who does not
    exist. That is the single-record form of the rule the list endpoint follows by
    returning zero rows: distinguishing "not yours" from "no such person" would confirm
    the person exists, which is itself the disclosure being prevented.
    """
    detail = await service.student_detail(request.session, request.scope, student_id)

    await request.record_rows(
        0 if detail is None else len(detail.subjects),
        detail=f"student={student_id}" + ("" if detail else " (not in scope)"),
    )
    await request.session.commit()

    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such student")

    # asdict recurses, so the nested rows arrive as plain dicts Pydantic can validate.
    return StudentDetailOut(**asdict(detail))

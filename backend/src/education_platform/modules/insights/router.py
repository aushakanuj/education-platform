"""One endpoint, three roles, three different answers -- from the same query."""

from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, Query
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

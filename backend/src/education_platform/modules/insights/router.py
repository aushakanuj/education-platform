"""One endpoint, three roles, three different answers -- from the same query."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from education_platform.api.deps import ScopedRequest, scoped
from education_platform.modules.audit.service import record_scoped_read
from education_platform.modules.insights import service

router = APIRouter(tags=["insights"])


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

    await record_scoped_read(
        request.session,
        principal=request.principal,
        scope=request.scope,
        resource="insights.students",
        rows_returned=len(rows),
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

    if request.scope.unrestricted:
        description = "Whole institution"
    elif not request.scope.student_ids:
        description = "No students in scope"
    else:
        description = (
            f"{len(request.scope.student_ids)} students across "
            f"{len(request.scope.offering_sections)} assignments"
        )

    return StudentSummaryPage(
        scope_description=description,
        rows_returned=len(rows),
        items=[StudentSummaryOut(**row.__dict__) for row in rows],
    )

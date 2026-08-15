"""Read the student_360 master register, always through a Scope.

This is the pattern every later feature copies: the caller writes the *question*, and this
module appends the *boundary*. Dashboards, ask-the-data and the early-warning engine all
read here rather than assembling their own joins, so a permission fix lands in one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Select, and_, false, select
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.modules.authorization.scope import Scope
from education_platform.modules.insights.models import student_360

#: Hard ceiling on any single read, so no question can pull the whole school by accident.
MAX_ROWS = 500


@dataclass(frozen=True, slots=True)
class Student360Row:
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


def scope_predicate(scope: Scope) -> ColumnElement[bool]:
    """The SQL predicate narrowing student_360 to what `scope` permits.

    Public and separate so the text-to-SQL guardrail (task 2.3) reuses exactly this
    predicate instead of reimplementing it. Institution is always pinned; an administrator
    is narrowed no further; anyone else is narrowed to their resolved student list.

    A principal who can reach no students compiles to `false` -- an empty result set,
    deliberately not an error, because an error would confirm that the data they asked
    about exists.
    """
    institution = student_360.c.institution_id == scope.institution_id
    if scope.unrestricted:
        return institution
    if not scope.student_ids:
        return false()
    return and_(institution, student_360.c.student_id.in_(sorted(scope.student_ids, key=str)))


def scoped_select(scope: Scope) -> Select[Any]:
    """A SELECT over the register with the boundary already applied."""
    return select(
        student_360.c.student_id,
        student_360.c.full_name,
        student_360.c.student_identifier,
        student_360.c.grade,
        student_360.c.section,
        student_360.c.subject,
        student_360.c.academic_period,
        student_360.c.quizzes_taken,
        student_360.c.quizzes_passed,
        student_360.c.mastery_percent,
        student_360.c.lessons_completed,
        student_360.c.attendance_percent,
    ).where(scope_predicate(scope))


async def query_student_360(
    session: AsyncSession,
    scope: Scope,
    *,
    subject: str | None = None,
    grade: str | None = None,
    section: str | None = None,
    limit: int = 100,
) -> list[Student360Row]:
    """Rows from the master register that this scope permits, and no others."""
    statement = scoped_select(scope)

    if subject:
        statement = statement.where(student_360.c.subject == subject)
    if grade:
        statement = statement.where(student_360.c.grade == grade)
    if section:
        statement = statement.where(student_360.c.section == section)

    statement = statement.order_by(
        student_360.c.mastery_percent.asc(), student_360.c.full_name.asc()
    ).limit(max(1, min(limit, MAX_ROWS)))

    result = await session.execute(statement)
    return [
        Student360Row(
            student_id=row.student_id,
            full_name=row.full_name,
            student_identifier=row.student_identifier,
            grade=row.grade,
            section=row.section,
            subject=row.subject,
            academic_period=row.academic_period,
            quizzes_taken=int(row.quizzes_taken or 0),
            quizzes_passed=int(row.quizzes_passed or 0),
            mastery_percent=float(row.mastery_percent or 0.0),
            lessons_completed=int(row.lessons_completed or 0),
            attendance_percent=(
                float(row.attendance_percent) if row.attendance_percent is not None else None
            ),
        )
        for row in result.mappings().all()
    ]

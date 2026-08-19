"""Read the student_360 master register, always through a Scope.

This is the pattern every later feature copies: the caller writes the *question*, and this
module appends the *boundary*. Dashboards, ask-the-data and the early-warning engine all
read here rather than assembling their own joins, so a permission fix lands in one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Select, and_, false, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.modules.assessments.models import (
    CommonMasteryQuiz,
    QuizAttempt,
    QuizAttemptStatus,
    QuizVersion,
)
from education_platform.modules.attendance.models import AttendanceRecord, AttendanceStatus
from education_platform.modules.authorization.scope import Scope
from education_platform.modules.insights.models import student_360

#: Hard ceiling on any single read, so no question can pull the whole school by accident.
MAX_ROWS = 500

#: How much of one student's history the detail view carries back. Enough to see a trend
#: without turning a page open into a full export.
MAX_ATTEMPTS = 25
MAX_ABSENCES = 10


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


@dataclass(frozen=True, slots=True)
class SubjectStanding:
    """One subject of one student, as far as the caller is permitted to see it."""

    subject: str
    quizzes_taken: int
    quizzes_passed: int
    mastery_percent: float
    lessons_started: int
    lessons_completed: int
    last_attempt_at: datetime | None


@dataclass(frozen=True, slots=True)
class AttemptRow:
    attempt_id: UUID
    subject: str
    quiz_title: str
    attempt_number: int
    score_percent: float | None
    passed: bool | None
    submitted_at: datetime | None


@dataclass(frozen=True, slots=True)
class AbsenceRow:
    on_date: date
    status: str


@dataclass(frozen=True, slots=True)
class StudentDetail:
    """Everything one screen needs about one student, already narrowed to the caller.

    `subjects` and `attempts` cover only the subjects the caller may see; `attendance` is
    whole-day and so is not divided by subject at all.
    """

    student_id: UUID
    full_name: str
    student_identifier: str
    grade: str
    section: str | None
    academic_period: str
    subjects: list[SubjectStanding]
    attempts: list[AttemptRow]
    days_present: int
    days_counted: int
    attendance_percent: float | None
    absences: list[AbsenceRow]


def _taught_predicate(scope: Scope) -> ColumnElement[bool] | None:
    """Rows for the exact (offering, section) pairs the principal teaches.

    An assignment naming no section covers every section of that offering. One that names a
    section matches only that section -- a row whose `section_id` is NULL (a student
    enrolled in a grade but not placed in a section) therefore does not match, which is the
    safe direction to fail.
    """
    if not scope.taught_offering_sections:
        return None

    whole_offerings = sorted(
        (offering for offering, section in scope.taught_offering_sections if section is None),
        key=str,
    )
    exact_pairs = sorted(
        ((o, s) for o, s in scope.taught_offering_sections if s is not None),
        key=lambda pair: (str(pair[0]), str(pair[1])),
    )

    clauses: list[ColumnElement[bool]] = []
    if whole_offerings:
        clauses.append(student_360.c.grade_subject_offering_id.in_(whole_offerings))
    if exact_pairs:
        clauses.append(
            tuple_(student_360.c.grade_subject_offering_id, student_360.c.section_id).in_(
                exact_pairs
            )
        )
    return clauses[0] if len(clauses) == 1 else or_(*clauses)


def scope_predicate(scope: Scope) -> ColumnElement[bool]:
    """The SQL predicate narrowing student_360 to what `scope` permits.

    Public and separate so the text-to-SQL guardrail (task 2.3) reuses exactly this
    predicate instead of reimplementing it. Institution is always pinned; an administrator
    is narrowed no further; everyone else reaches a row by exactly one of two routes:

    * it is their own student record -- every subject of it, and
    * it belongs to an (offering, section) pair they teach.

    Filtering on the student list alone is not enough, and was the bug this shape fixes: a
    Grade 8 Mathematics teacher reaches those pupils, but each pupil also has Science and
    English rows in the register, and a student filter lets all of them through. The grain
    of `student_360` is student *per subject*, so the boundary has to be too.

    A principal who can reach nothing compiles to `false` -- an empty result set,
    deliberately not an error, because an error would confirm that the data they asked
    about exists.
    """
    institution = student_360.c.institution_id == scope.institution_id
    if scope.unrestricted:
        return institution

    grants: list[ColumnElement[bool]] = []
    if scope.self_student_id is not None:
        grants.append(student_360.c.student_id == scope.self_student_id)
    taught = _taught_predicate(scope)
    if taught is not None:
        grants.append(taught)

    if not grants:
        return false()
    return and_(institution, grants[0] if len(grants) == 1 else or_(*grants))


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


#: Attempts a teacher has any business seeing: ones the student actually finished.
_FINISHED_ATTEMPTS = (
    QuizAttemptStatus.SUBMITTED,
    QuizAttemptStatus.SCORED,
    QuizAttemptStatus.RELEASED,
)


async def student_detail(
    session: AsyncSession,
    scope: Scope,
    student_id: UUID,
) -> StudentDetail | None:
    """One student's record, narrowed to the subjects the caller may see.

    Returns `None` when the caller may see nothing about this student -- whether because no
    such student exists or because they are outside the boundary. The two are deliberately
    indistinguishable, for the same reason an out-of-scope list read returns zero rows: a
    "not permitted" that differs from a "no such student" confirms the student exists.

    The boundary is applied exactly once, by `scope_predicate`, and everything else follows
    from its result. The register rows carry `student_subject_enrollment_id`, so the set of
    enrolments the caller may see falls out of the same query -- and filtering the attempt
    history on that set means a Mathematics teacher gets Mathematics attempts and nothing
    else, without a second permission rule written here. An attempt whose enrolment is NULL
    is therefore excluded: unattributable, so not shown, which is the safe direction.
    """
    register = (
        (
            await session.execute(
                select(
                    student_360.c.student_id,
                    student_360.c.full_name,
                    student_360.c.student_identifier,
                    student_360.c.grade,
                    student_360.c.section,
                    student_360.c.academic_period,
                    student_360.c.subject,
                    student_360.c.student_subject_enrollment_id,
                    student_360.c.quizzes_taken,
                    student_360.c.quizzes_passed,
                    student_360.c.mastery_percent,
                    student_360.c.lessons_started,
                    student_360.c.lessons_completed,
                    student_360.c.last_attempt_at,
                    student_360.c.days_present,
                    student_360.c.days_counted,
                    student_360.c.attendance_percent,
                )
                .where(scope_predicate(scope), student_360.c.student_id == student_id)
                .order_by(student_360.c.subject.asc())
            )
        )
        .mappings()
        .all()
    )

    if not register:
        return None

    head = register[0]
    subject_of_enrolment = {
        row.student_subject_enrollment_id: row.subject
        for row in register
        if row.student_subject_enrollment_id is not None
    }

    return StudentDetail(
        student_id=head.student_id,
        full_name=head.full_name,
        student_identifier=head.student_identifier,
        grade=head.grade,
        section=head.section,
        academic_period=head.academic_period,
        subjects=[
            SubjectStanding(
                subject=row.subject,
                quizzes_taken=int(row.quizzes_taken or 0),
                quizzes_passed=int(row.quizzes_passed or 0),
                mastery_percent=float(row.mastery_percent or 0.0),
                lessons_started=int(row.lessons_started or 0),
                lessons_completed=int(row.lessons_completed or 0),
                last_attempt_at=row.last_attempt_at,
            )
            for row in register
        ],
        attempts=await _permitted_attempts(session, student_id, subject_of_enrolment),
        # Whole-day figures repeat on every subject row of the same student, so any row
        # carries them. See the `attendance_stats` CTE in migration d3e4f5a6b7c8.
        days_present=int(head.days_present or 0),
        days_counted=int(head.days_counted or 0),
        attendance_percent=(
            float(head.attendance_percent) if head.attendance_percent is not None else None
        ),
        absences=await _recent_absences(session, student_id),
    )


async def _permitted_attempts(
    session: AsyncSession,
    student_id: UUID,
    subject_of_enrolment: dict[UUID, str],
) -> list[AttemptRow]:
    """The student's finished attempts, in the subjects `subject_of_enrolment` permits."""
    if not subject_of_enrolment:
        return []

    rows = await session.execute(
        select(
            QuizAttempt.id,
            QuizAttempt.student_subject_enrollment_id,
            QuizAttempt.attempt_number,
            QuizAttempt.score_percent,
            QuizAttempt.passed,
            QuizAttempt.submitted_at,
            CommonMasteryQuiz.title,
        )
        .join(QuizVersion, QuizVersion.id == QuizAttempt.quiz_version_id)
        .join(CommonMasteryQuiz, CommonMasteryQuiz.id == QuizVersion.quiz_id)
        .where(
            QuizAttempt.student_id == student_id,
            QuizAttempt.student_subject_enrollment_id.in_(subject_of_enrolment),
            QuizAttempt.status.in_(_FINISHED_ATTEMPTS),
        )
        .order_by(QuizAttempt.submitted_at.desc().nullslast())
        .limit(MAX_ATTEMPTS)
    )

    return [
        AttemptRow(
            attempt_id=row.id,
            subject=subject_of_enrolment[row.student_subject_enrollment_id],
            quiz_title=row.title,
            attempt_number=int(row.attempt_number),
            score_percent=(float(row.score_percent) if row.score_percent is not None else None),
            passed=row.passed,
            submitted_at=row.submitted_at,
        )
        for row in rows.all()
    ]


async def _recent_absences(session: AsyncSession, student_id: UUID) -> list[AbsenceRow]:
    """Recent days the student was not simply present, whole-day records only.

    Not narrowed by subject because whole-day attendance is not a subject's to divide: it
    is the same fact for every teacher of the child, and it is the figure the 75%
    eligibility rule is measured against.
    """
    rows = await session.execute(
        select(AttendanceRecord.on_date, AttendanceRecord.status)
        .where(
            AttendanceRecord.student_id == student_id,
            AttendanceRecord.grade_subject_offering_id.is_(None),
            AttendanceRecord.status != AttendanceStatus.PRESENT,
        )
        .order_by(AttendanceRecord.on_date.desc())
        .limit(MAX_ABSENCES)
    )
    return [AbsenceRow(on_date=on_date, status=status.value) for on_date, status in rows.all()]

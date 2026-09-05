"""Compute, store, list, and dismiss at-risk flags -- the only module that touches the
database on this feature's behalf. `engine.py` decides *whether* a flag exists; this module
decides *where the numbers come from* and *who is allowed to see the result*, and reuses
`authorization.predicate` for the second question rather than answering it itself (spec
Section 7.1 -- this is Rule 7 from the permission model, applied here on purpose).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.modules.academics.models import GradeSubjectOffering, Subject
from education_platform.modules.assessments.models import QuizAttempt, QuizAttemptStatus
from education_platform.modules.at_risk.engine import (
    DEFAULT_THRESHOLDS,
    EngineFlag,
    StudentSignals,
    SubjectSignal,
    Thresholds,
    evaluate_student,
)
from education_platform.modules.at_risk.models import AtRiskFlag, AtRiskStatus, AtRiskTier
from education_platform.modules.audit.service import AuditAction, record_event
from education_platform.modules.auth.models import StudentProfile
from education_platform.modules.authorization.predicate import ScopeColumns, scope_predicate_for
from education_platform.modules.authorization.scope import Scope
from education_platform.modules.insights.models import student_360

#: How the flags table names the four concepts the boundary reasons about. Same reuse
#: point every other governed table uses -- see `insights.service.STUDENT_360_COLUMNS`.
#: The `cast`s are for mypy only: an ORM `Mapped[...]` attribute satisfies `ColumnElement`
#: at runtime (that is how every `.where(Model.column == ...)` call in this codebase
#: works) but is typed as `InstrumentedAttribute`, which `ScopeColumns` does not declare
#: as an accepted type. `insights.service` sidesteps this by building `ScopeColumns` from
#: a Core `Table`'s `.c.column` instead, which mypy does see as a `ColumnElement` -- not
#: available here since `AtRiskFlag` is declared as an ORM class, not a Core table.
AT_RISK_FLAG_COLUMNS = ScopeColumns(
    institution_id=cast("ColumnElement[Any]", AtRiskFlag.institution_id),
    student_id=cast("ColumnElement[Any]", AtRiskFlag.student_id),
    grade_subject_offering_id=cast("ColumnElement[Any]", AtRiskFlag.grade_subject_offering_id),
    section_id=cast("ColumnElement[Any]", AtRiskFlag.section_id),
)


def flag_scope_predicate(scope: Scope) -> ColumnElement[bool]:
    """The permission boundary, bound to `at_risk_flags`.

    `section_id` here is the flagged *student's* class section (from their grade
    enrolment), not a property of the concern itself -- a flag is about a subject, not a
    class register. An earlier version of this function aliased `section_id` to the
    `grade_subject_offering_id` column to avoid adding a real one, reasoning that the
    exact-(offering, section) branch of the teacher grant would become harmlessly
    redundant with the whole-offering branch. That reasoning was wrong, and
    test_at_risk_api.py caught it: most real teaching assignments in this codebase name a
    specific section rather than a whole offering (confirmed against the live synthetic
    school), so a teacher whose assignment is an exact (offering, section) pair was
    matched against a fabricated pair of (offering, offering) that could never equal
    theirs -- every section-scoped teacher saw zero flags for anything they taught. A real
    `section_id` column (migration f8c841992918) is what actually makes the shared
    predicate's exact-pair grant work here, the same way it works for `student_360`.

    The one property that *does* still fall out of the shared predicate for free: an
    attendance-only flag (`grade_subject_offering_id IS NULL`) fails both of a teacher's
    grant branches -- NULL cannot equal or be IN a set of real offering ids, with or
    without a section attached -- and passes only the unrestricted (administrator)
    branch. Section 7.2's "administrators only" rule for attendance-only flags needed no
    special-case code precisely because that part of the reasoning was correct.
    """
    return scope_predicate_for(scope, AT_RISK_FLAG_COLUMNS)


@dataclass(frozen=True, slots=True)
class FlagRow:
    id: UUID
    student_id: UUID
    student_name: str
    grade_subject_offering_id: UUID | None
    subject: str | None
    tier: str
    drivers: list[dict[str, object]]
    status: str
    computed_at: datetime
    dismissed_by_user_id: UUID | None
    dismissed_at: datetime | None
    dismissal_note: str | None


async def list_flags(session: AsyncSession, scope: Scope, *, limit: int = 200) -> list[FlagRow]:
    """Flags this caller may see, and no others -- the row-level half of Section 7.2.

    The capability half (a student must never reach this at all, regardless of what their
    own Scope would technically permit) is enforced one layer up, by the router's
    `require_role`. Both layers matter: `Scope.self_student_id` grants a principal their
    own rows on any table using it, which is exactly right for `student_360` and exactly
    wrong here -- a student must never see their own at-risk flag (spec Section 7.3). This
    module does not special-case that; it relies on the router never calling it for a
    student in the first place. See
    test_at_risk_api.py::test_a_student_cannot_reach_the_endpoint_at_all.

    Names are resolved with two small, separate lookups rather than one JOIN against
    `student_360`: that view has one row per (student, subject), so joining it directly
    against a table that can have `grade_subject_offering_id IS NULL` (an attendance-only
    flag) would fan out into one duplicate result row per subject the student takes. Two
    flat, keyed-by-id lookups avoid that entirely rather than working around it.
    """
    flags = (
        (
            await session.execute(
                select(AtRiskFlag)
                .where(flag_scope_predicate(scope), AtRiskFlag.status == AtRiskStatus.ACTIVE)
                .order_by(AtRiskFlag.tier.desc(), AtRiskFlag.computed_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    if not flags:
        return []

    student_ids = {flag.student_id for flag in flags}
    offering_ids = {
        flag.grade_subject_offering_id for flag in flags if flag.grade_subject_offering_id
    }

    names_by_student: dict[UUID, str] = {
        row[0]: row[1]
        for row in (
            await session.execute(
                select(StudentProfile.id, StudentProfile.full_name).where(
                    StudentProfile.id.in_(student_ids)
                )
            )
        ).all()
    }
    subjects_by_offering: dict[UUID, str] = {}
    if offering_ids:
        subjects_by_offering = {
            row[0]: row[1]
            for row in (
                await session.execute(
                    select(GradeSubjectOffering.id, Subject.name)
                    .join(Subject, Subject.id == GradeSubjectOffering.subject_id)
                    .where(GradeSubjectOffering.id.in_(offering_ids))
                )
            ).all()
        }

    return [
        FlagRow(
            id=flag.id,
            student_id=flag.student_id,
            student_name=names_by_student.get(flag.student_id, "Unknown"),
            grade_subject_offering_id=flag.grade_subject_offering_id,
            subject=(
                subjects_by_offering.get(flag.grade_subject_offering_id)
                if flag.grade_subject_offering_id
                else None
            ),
            tier=flag.tier,
            drivers=flag.drivers,
            status=flag.status,
            computed_at=flag.computed_at,
            dismissed_by_user_id=flag.dismissed_by_user_id,
            dismissed_at=flag.dismissed_at,
            dismissal_note=flag.dismissal_note,
        )
        for flag in flags
    ]


async def record_flag_view(
    session: AsyncSession, *, institution_id: UUID, actor_user_id: UUID, rows_returned: int
) -> None:
    """AR-5: a flag view is a scoped, audited read like any other analytics access."""
    await record_event(
        session,
        institution_id=institution_id,
        actor_user_id=actor_user_id,
        event_type=AuditAction.VIEW_FLAGS,
        entity_type="at_risk.flags",
        payload={"rows_returned": rows_returned},
    )


class NotInScopeError(Exception):
    """Raised when a caller tries to dismiss a flag outside what their Scope permits."""


async def dismiss_flag(
    session: AsyncSession,
    scope: Scope,
    *,
    flag_id: UUID,
    actor_user_id: UUID,
    institution_id: UUID,
    note: str | None,
) -> FlagRow | None:
    """AR-4: dismiss a flag, and audit the action regardless of outcome-adjacent details.

    Returns None if no such flag exists *or* it exists outside the caller's scope -- the
    same empty-not-refused answer as every other boundary in this codebase (spec Section
    4's reuse of doc 02 Section 11a.3), so a teacher probing flag ids cannot learn which
    ones exist for a child they do not teach.
    """
    statement = select(AtRiskFlag).where(
        AtRiskFlag.id == flag_id,
        flag_scope_predicate(scope),
        AtRiskFlag.status == AtRiskStatus.ACTIVE,
    )
    flag = (await session.execute(statement)).scalar_one_or_none()
    if flag is None:
        return None

    flag.status = AtRiskStatus.DISMISSED
    flag.dismissed_by_user_id = actor_user_id
    flag.dismissed_at = datetime.now(UTC)
    flag.dismissal_note = note
    await session.flush()

    await record_event(
        session,
        institution_id=institution_id,
        actor_user_id=actor_user_id,
        event_type=AuditAction.RECORD_INTERVENTION,
        entity_type="at_risk.flag",
        entity_id=flag.id,
        payload={"action": "dismiss", "student_id": str(flag.student_id)},
    )

    return FlagRow(
        id=flag.id,
        student_id=flag.student_id,
        student_name="",
        grade_subject_offering_id=flag.grade_subject_offering_id,
        subject=None,
        tier=flag.tier,
        drivers=flag.drivers,
        status=flag.status,
        computed_at=flag.computed_at,
        dismissed_by_user_id=flag.dismissed_by_user_id,
        dismissed_at=flag.dismissed_at,
        dismissal_note=flag.dismissal_note,
    )


#: Attempts that count toward mastery and trend -- mirrors insights.service._FINISHED_ATTEMPTS.
_FINISHED = (QuizAttemptStatus.SUBMITTED, QuizAttemptStatus.SCORED, QuizAttemptStatus.RELEASED)


async def _signals_for_institution(
    session: AsyncSession, institution_id: UUID
) -> list[StudentSignals]:
    """Every student's raw signals, unrestricted within one institution.

    Deliberately not scope-filtered: computing flags for the whole school is an
    administrative action (gated by `require_role("administrator")` at the router), not a
    read on behalf of one teacher's narrower view. The *output* rows are still tagged with
    `institution_id`/`student_id`/`grade_subject_offering_id`, so every later *read* of
    them goes through `flag_scope_predicate` regardless of how they were computed.
    """
    register = (
        (
            await session.execute(
                select(
                    student_360.c.student_id,
                    student_360.c.academic_period_id,
                    student_360.c.grade_subject_offering_id,
                    student_360.c.mastery_percent,
                    student_360.c.quizzes_taken,
                    student_360.c.attendance_percent,
                    student_360.c.student_subject_enrollment_id,
                ).where(student_360.c.institution_id == institution_id)
            )
        )
        .mappings()
        .all()
    )

    enrolment_ids = [
        row.student_subject_enrollment_id
        for row in register
        if row.student_subject_enrollment_id is not None and row.quizzes_taken > 0
    ]
    scores_by_enrolment: dict[UUID, list[float]] = defaultdict(list)
    if enrolment_ids:
        attempt_rows = await session.execute(
            select(QuizAttempt.student_subject_enrollment_id, QuizAttempt.score_percent)
            .where(
                QuizAttempt.student_subject_enrollment_id.in_(enrolment_ids),
                QuizAttempt.status.in_(_FINISHED),
                QuizAttempt.score_percent.is_not(None),
            )
            .order_by(QuizAttempt.student_subject_enrollment_id, QuizAttempt.submitted_at.desc())
        )
        for enrolment_id, score in attempt_rows.all():
            scores_by_enrolment[enrolment_id].append(float(score))

    @dataclass(slots=True)
    class _Bucket:
        attendance: float | None = None
        subjects: list[SubjectSignal] = field(default_factory=list)

    by_student: dict[UUID, _Bucket] = {}
    for row in register:
        bucket = by_student.setdefault(row.student_id, _Bucket())
        if row.grade_subject_offering_id is not None:
            scores = scores_by_enrolment.get(row.student_subject_enrollment_id, [])
            bucket.subjects.append(
                SubjectSignal(
                    grade_subject_offering_id=row.grade_subject_offering_id,
                    mastery_percent=float(row.mastery_percent or 0.0),
                    attempt_scores_recent_first=tuple(scores),
                )
            )
        if row.attendance_percent is not None:
            bucket.attendance = float(row.attendance_percent)

    return [
        StudentSignals(
            student_id=student_id,
            attendance_percent=bucket.attendance,
            subjects=tuple(bucket.subjects),
        )
        for student_id, bucket in by_student.items()
    ]


@dataclass(frozen=True, slots=True)
class RecomputeResult:
    students_considered: int
    flags_active: int
    flags_resolved: int


async def recompute_institution(
    session: AsyncSession,
    *,
    institution_id: UUID,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> RecomputeResult:
    """Run the engine for every student in an institution and persist the result.

    Upserts one active row per (student, subject) or (student, NULL-for-attendance) key
    the engine still flags; anything that *was* active but the engine no longer flags is
    marked `resolved`, not deleted -- the flag's history (who dismissed what, when) has
    value even after the underlying condition clears, per the audit trail's own logic.
    """
    signals = await _signals_for_institution(session, institution_id)

    # One row per student is enough for both of these: academic_period_id and section_id
    # are constant across every subject a student takes (section comes from the grade
    # enrolment, not the subject one) -- see migration f8c841992918's note on section_id.
    academic_period_by_student: dict[UUID, UUID] = {}
    section_by_student: dict[UUID, UUID | None] = {}
    all_students = (
        await session.execute(
            select(
                student_360.c.student_id,
                student_360.c.academic_period_id,
                student_360.c.section_id,
            ).where(student_360.c.institution_id == institution_id)
        )
    ).all()
    for student_id, period_id, section_id in all_students:
        academic_period_by_student[student_id] = period_id
        section_by_student[student_id] = section_id

    now = datetime.now(UTC)
    new_keys: set[tuple[UUID, UUID | None]] = set()

    for student_signals in signals:
        flags: list[EngineFlag] = evaluate_student(student_signals, thresholds)
        for flag in flags:
            key = (student_signals.student_id, flag.grade_subject_offering_id)
            new_keys.add(key)
            await _upsert_flag(
                session,
                institution_id=institution_id,
                student_id=student_signals.student_id,
                academic_period_id=academic_period_by_student[student_signals.student_id],
                section_id=section_by_student.get(student_signals.student_id),
                flag=flag,
                computed_at=now,
            )

    resolved = await _resolve_stale_flags(session, institution_id=institution_id, keep=new_keys)
    await session.flush()

    return RecomputeResult(
        students_considered=len(signals),
        flags_active=len(new_keys),
        flags_resolved=resolved,
    )


async def _upsert_flag(
    session: AsyncSession,
    *,
    institution_id: UUID,
    student_id: UUID,
    academic_period_id: UUID,
    section_id: UUID | None,
    flag: EngineFlag,
    computed_at: datetime,
) -> None:
    drivers_payload = [
        {
            "metric": driver.metric,
            "value": driver.value,
            "comparison": driver.comparison,
            "window": driver.window,
        }
        for driver in flag.drivers
    ]

    existing = (
        await session.execute(
            select(AtRiskFlag).where(
                AtRiskFlag.student_id == student_id,
                AtRiskFlag.grade_subject_offering_id.is_(flag.grade_subject_offering_id)
                if flag.grade_subject_offering_id is None
                else AtRiskFlag.grade_subject_offering_id == flag.grade_subject_offering_id,
                AtRiskFlag.status == AtRiskStatus.ACTIVE,
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.tier = AtRiskTier(flag.tier)
        existing.drivers = drivers_payload
        existing.computed_at = computed_at
        existing.section_id = section_id
        return

    session.add(
        AtRiskFlag(
            institution_id=institution_id,
            student_id=student_id,
            grade_subject_offering_id=flag.grade_subject_offering_id,
            section_id=section_id,
            academic_period_id=academic_period_id,
            tier=AtRiskTier(flag.tier),
            drivers=drivers_payload,
            status=AtRiskStatus.ACTIVE,
            computed_at=computed_at,
        )
    )


async def _resolve_stale_flags(
    session: AsyncSession, *, institution_id: UUID, keep: set[tuple[UUID, UUID | None]]
) -> int:
    """Mark `resolved` any active flag not reproduced by the run that just finished."""
    active = (
        (
            await session.execute(
                select(AtRiskFlag).where(
                    AtRiskFlag.institution_id == institution_id,
                    AtRiskFlag.status == AtRiskStatus.ACTIVE,
                )
            )
        )
        .scalars()
        .all()
    )

    resolved_count = 0
    for row in active:
        if (row.student_id, row.grade_subject_offering_id) not in keep:
            row.status = AtRiskStatus.RESOLVED
            resolved_count += 1
    return resolved_count

"""Postgres-backed integration tests for apply_role_scope.

Unlike test_text_to_sql_apply_role_scope.py (pure sqlglot AST inspection, no DB), these
tests seed real rows and execute the SQL apply_role_scope actually produces against a
live database, via the same `clean_db`/Postgres fixtures test_authorization_scope.py uses.

Two things this file establishes that the AST-only tests can't:

1. Real-data proof of the `teaching_assignments.section_id IS NULL` = "all sections"
   rule (and its opposite, a specific-section assignment excluding other sections) —
   not just that the generated predicate *text* contains the right clause, but that it
   actually filters real rows the right way.
2. A cross-check against `education_platform.modules.insights.service.scope_predicate()`
   (the `student_360`-only, `Scope`-based implementation apply_role_scope's own module
   docstring explains it could *not* reuse directly). These two implementations now
   encode the same row-visibility rules independently; this file is the evidence they
   still agree. It does not need to run on every CI build forever, but it needs to exist
   and pass now, and it should be re-run — and probably re-verified — any time either
   `apply_role_scope.py`'s row-predicate builders or `authorization/scope.py` /
   `insights/service.py`'s `Scope`/`scope_predicate()` change, since nothing else will
   catch the two drifting apart.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from education_platform.db.url import to_async_url, to_sync_url
from education_platform.modules.academics.models import (
    AcademicPeriod,
    AcademicPeriodStatus,
    EnrollmentStatus,
    Grade,
    GradeSubjectOffering,
    PeriodGrade,
    Section,
    StudentGradeEnrollment,
    StudentSubjectEnrollment,
    Subject,
    TeachingAssignment,
    TeachingAssignmentStatus,
)
from education_platform.modules.attendance.models import AttendanceRecord, AttendanceStatus
from education_platform.modules.auth.models import (
    Institution,
    RoleName,
    StudentProfile,
    User,
    UserRole,
)
from education_platform.modules.authorization.scope import scope_for
from education_platform.modules.insights.models import student_360
from education_platform.modules.insights.service import scope_predicate
from education_platform.modules.text_to_sql.nodes.apply_role_scope import apply_role_scope
from education_platform.modules.text_to_sql.state import TextToSQLState


@dataclass(frozen=True)
class _Fixture:
    institution_id: UUID
    other_institution_id: UUID

    teacher_user_id: UUID
    admin_user_id: UUID

    section_a_id: UUID  # "8A" — the teacher's Math assignment names this section only
    section_b_id: UUID  # "8B" — outside the Math assignment; inside the NULL-section one

    # Logged-in student in Math/8A: reached by the teacher's *specific*-section grant.
    student_a_math_id: UUID
    student_a_math_user_id: UUID

    # Logged-in student in Math/8B: same subject, wrong section — must be excluded.
    student_b_math_id: UUID

    # Logged-in student in Science/8A: reached only via the NULL-section ("all sections")
    # grant, since the teacher's Science assignment names no section.
    student_a_science_id: UUID

    # Provisioned student, Science/8B, NO login (student_profiles.user_id IS NULL) —
    # reached via the same NULL-section grant. Exercises the schema catalog's
    # student_profiles.user_id nullability caveat: this row can never be anyone's *self*
    # match (NULL never equals a literal in SQL), but a teacher's grant must still see it
    # exactly like a logged-in student's row would be seen.
    student_b_science_provisioned_id: UUID

    # A different institution's student, structurally identical to the above (same grade
    # name, same shape) but must never appear in institution_id's own results.
    other_student_id: UUID


def _seed(session: Session) -> _Fixture:
    inst1 = Institution(name="ARS Integration Test School", timezone="UTC")
    inst2 = Institution(name="ARS Integration Test School — Other Institution", timezone="UTC")
    session.add_all([inst1, inst2])
    session.flush()

    period = AcademicPeriod(
        institution_id=inst1.id,
        name="Term 1",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 6, 30),
        status=AcademicPeriodStatus.ACTIVE,
    )
    grade = Grade(institution_id=inst1.id, name="Grade 8")
    subject_math = Subject(institution_id=inst1.id, name="Mathematics", code="MATH")
    subject_science = Subject(institution_id=inst1.id, name="Science", code="SCI")
    session.add_all([period, grade, subject_math, subject_science])
    session.flush()

    period_grade = PeriodGrade(academic_period_id=period.id, grade_id=grade.id)
    session.add(period_grade)
    session.flush()

    section_a = Section(period_grade_id=period_grade.id, name="8A")
    section_b = Section(period_grade_id=period_grade.id, name="8B")
    session.add_all([section_a, section_b])
    session.flush()

    offering_math = GradeSubjectOffering(
        period_grade_id=period_grade.id, subject_id=subject_math.id
    )
    offering_science = GradeSubjectOffering(
        period_grade_id=period_grade.id, subject_id=subject_science.id
    )
    session.add_all([offering_math, offering_science])
    session.flush()

    teacher = User(
        institution_id=inst1.id,
        email="teacher@ars-integration.school",
        full_name="Teacher",
        password_hash="unused",
    )
    admin = User(
        institution_id=inst1.id,
        email="admin@ars-integration.school",
        full_name="Admin",
        password_hash="unused",
    )
    session.add_all([teacher, admin])
    session.flush()
    session.add_all(
        [
            UserRole(user_id=teacher.id, role=RoleName.TEACHER),
            UserRole(user_id=admin.id, role=RoleName.ADMINISTRATOR),
        ]
    )

    # Specific-section grant: Math, 8A only.
    session.add(
        TeachingAssignment(
            teacher_user_id=teacher.id,
            academic_period_id=period.id,
            grade_subject_offering_id=offering_math.id,
            section_id=section_a.id,
            status=TeachingAssignmentStatus.ACTIVE,
        )
    )
    # All-sections grant: Science, section_id NULL.
    session.add(
        TeachingAssignment(
            teacher_user_id=teacher.id,
            academic_period_id=period.id,
            grade_subject_offering_id=offering_science.id,
            section_id=None,
            status=TeachingAssignmentStatus.ACTIVE,
        )
    )

    def _enroll_student(
        *, identifier: str, section: Section, offering: GradeSubjectOffering, with_login: bool
    ) -> StudentProfile:
        user_id: UUID | None = None
        if with_login:
            user = User(
                institution_id=inst1.id,
                email=f"{identifier}@ars-integration.school",
                full_name=identifier,
                password_hash="unused",
            )
            session.add(user)
            session.flush()
            user_id = user.id

        profile = StudentProfile(
            institution_id=inst1.id,
            user_id=user_id,
            student_identifier=identifier,
            full_name=identifier,
        )
        session.add(profile)
        session.flush()

        grade_enrollment = StudentGradeEnrollment(
            student_id=profile.id,
            academic_period_id=period.id,
            period_grade_id=period_grade.id,
            section_id=section.id,
            status=EnrollmentStatus.ACTIVE,
        )
        session.add(grade_enrollment)
        session.flush()
        session.add(
            StudentSubjectEnrollment(
                student_id=profile.id,
                grade_enrollment_id=grade_enrollment.id,
                grade_subject_offering_id=offering.id,
                status=EnrollmentStatus.ACTIVE,
            )
        )
        session.add(
            AttendanceRecord(
                student_id=profile.id,
                academic_period_id=period.id,
                section_id=section.id,
                grade_subject_offering_id=offering.id,
                on_date=date(2026, 2, 1),
                status=AttendanceStatus.PRESENT,
            )
        )
        session.flush()
        return profile

    student_a_math = _enroll_student(
        identifier="stu-a-math", section=section_a, offering=offering_math, with_login=True
    )
    student_b_math = _enroll_student(
        identifier="stu-b-math", section=section_b, offering=offering_math, with_login=True
    )
    student_a_science = _enroll_student(
        identifier="stu-a-science", section=section_a, offering=offering_science, with_login=True
    )
    student_b_science_provisioned = _enroll_student(
        identifier="stu-b-science-noauth",
        section=section_b,
        offering=offering_science,
        with_login=False,
    )

    # Institution 2: overlapping-looking (same grade name, same shape) but must stay
    # invisible to institution 1's admin.
    other_student = StudentProfile(
        institution_id=inst2.id,
        user_id=None,
        student_identifier="other-inst-student",
        full_name="Other Institution Student",
    )
    session.add(other_student)
    session.flush()

    assert student_a_math.user_id is not None
    return _Fixture(
        institution_id=inst1.id,
        other_institution_id=inst2.id,
        teacher_user_id=teacher.id,
        admin_user_id=admin.id,
        section_a_id=section_a.id,
        section_b_id=section_b.id,
        student_a_math_id=student_a_math.id,
        student_a_math_user_id=student_a_math.user_id,
        student_b_math_id=student_b_math.id,
        student_a_science_id=student_a_science.id,
        student_b_science_provisioned_id=student_b_science_provisioned.id,
        other_student_id=other_student.id,
    )


@pytest.fixture()
def seeded(clean_db: str) -> Iterator[_Fixture]:
    engine = create_engine(to_sync_url(clean_db), pool_pre_ping=True)
    with Session(engine) as session:
        fixture = _seed(session)
        session.commit()
    engine.dispose()
    yield fixture


@pytest_asyncio.fixture()
async def async_session(seeded: _Fixture, clean_db: str) -> AsyncIterator[AsyncSession]:
    _ = seeded  # dependency only: must be seeded before this session reads
    engine = create_async_engine(to_async_url(clean_db), pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session
    await engine.dispose()


@dataclass(frozen=True)
class _FakePrincipal:
    """Stands in for api.deps.Principal, mirroring test_authorization_scope.py's."""

    user_id: UUID
    institution_id: UUID
    email: str
    roles: frozenset[str]
    student_profile_id: UUID | None
    status: str = "active"


async def _run_scoped(
    async_session: AsyncSession,
    *,
    sql: str,
    user_id: UUID,
    role: str,
    institution_id: UUID,
) -> list[dict[str, Any]]:
    """Runs `sql` through apply_role_scope for the given identity, then actually
    executes the rewritten SQL — not just inspects it — against the live database.
    """
    state: TextToSQLState = {
        "question": "irrelevant to this node",
        "user_id": str(user_id),
        "user_role": role,
        "institution_id": str(institution_id),
        "validated_sql": sql,
        "error": None,
        "retry_count": 0,
        "audit_entry": None,
    }
    result = await apply_role_scope(state)
    assert result["error"] is None, result["error"]
    validated = result.get("validated_sql")
    assert validated is not None
    rows = (await async_session.execute(text(validated))).mappings().all()
    return [dict(row) for row in rows]


# --- Item 2: real-data section_id IS NULL ("all sections") vs specific-section --------


async def test_teacher_row_scoping_against_real_attendance_data(
    async_session: AsyncSession, seeded: _Fixture
) -> None:
    rows = await _run_scoped(
        async_session,
        sql="SELECT ar.student_id FROM attendance_records ar",
        user_id=seeded.teacher_user_id,
        role="teacher",
        institution_id=seeded.institution_id,
    )
    student_ids = {row["student_id"] for row in rows}

    # The NULL-section (Science) grant reaches every section under that offering.
    assert seeded.student_a_science_id in student_ids
    assert seeded.student_b_science_provisioned_id in student_ids

    # The specific-section (Math, 8A) grant reaches only its own section, not 8B —
    # even though 8B studies the very same subject.
    assert seeded.student_a_math_id in student_ids
    assert seeded.student_b_math_id not in student_ids


# --- Item 3: cross-check against insights.service.scope_predicate() -------------------
#
# apply_role_scope.py could not reuse scope_predicate() directly (see that module's
# docstring) and reimplements the same row-visibility rules independently. These tests
# are the evidence the two still agree; re-run them whenever either side's row-predicate
# logic changes.


async def test_cross_check_teacher_scope_matches_scope_predicate(
    async_session: AsyncSession, seeded: _Fixture
) -> None:
    principal = _FakePrincipal(
        user_id=seeded.teacher_user_id,
        institution_id=seeded.institution_id,
        email="teacher@ars-integration.school",
        roles=frozenset({RoleName.TEACHER.value}),
        student_profile_id=None,
    )
    scope = await scope_for(async_session, principal)
    scope_predicate_rows = (
        await async_session.execute(
            select(student_360.c.student_id, student_360.c.section_id).where(
                scope_predicate(scope)
            )
        )
    ).all()
    scope_predicate_set = {(row.student_id, row.section_id) for row in scope_predicate_rows}

    node_rows = await _run_scoped(
        async_session,
        sql="SELECT student_id, section_id FROM student_360",
        user_id=seeded.teacher_user_id,
        role="teacher",
        institution_id=seeded.institution_id,
    )
    node_set = {(row["student_id"], row["section_id"]) for row in node_rows}

    assert scope_predicate_set == node_set
    assert scope_predicate_set, "the teacher must see at least one row, or this proves nothing"

    # Both named scenarios from the task write-up, in one comparison: a specific-section
    # assignment (Math/8A) and a section_id IS NULL assignment (Science, all sections) —
    # plus the "student with no login yet" case, reached only via the NULL-section grant,
    # never a self-match (student_profiles.user_id IS NULL can never equal a literal).
    assert (seeded.student_a_math_id, seeded.section_a_id) in node_set
    assert (seeded.student_a_science_id, seeded.section_a_id) in node_set
    assert (seeded.student_b_science_provisioned_id, seeded.section_b_id) in node_set
    assert (seeded.student_b_math_id, seeded.section_b_id) not in node_set


async def test_cross_check_student_scope_matches_scope_predicate(
    async_session: AsyncSession, seeded: _Fixture
) -> None:
    # "Student with no login yet" cannot itself be the querying principal — there is no
    # user_id to authenticate with. That case is exercised as *data* above, reached
    # through the teacher's grant; here the self-scope side of the cross-check uses the
    # one logged-in student, which is the only kind of principal a student query can be.
    principal = _FakePrincipal(
        user_id=seeded.student_a_math_user_id,
        institution_id=seeded.institution_id,
        email="stu-a-math@ars-integration.school",
        roles=frozenset({RoleName.STUDENT.value}),
        student_profile_id=seeded.student_a_math_id,
    )
    scope = await scope_for(async_session, principal)
    scope_predicate_rows = (
        await async_session.execute(
            select(student_360.c.student_id, student_360.c.section_id).where(
                scope_predicate(scope)
            )
        )
    ).all()
    scope_predicate_set = {(row.student_id, row.section_id) for row in scope_predicate_rows}

    node_rows = await _run_scoped(
        async_session,
        sql="SELECT student_id, section_id FROM student_360",
        user_id=seeded.student_a_math_user_id,
        role="student",
        institution_id=seeded.institution_id,
    )
    node_set = {(row["student_id"], row["section_id"]) for row in node_rows}

    assert scope_predicate_set == node_set
    assert scope_predicate_set == {(seeded.student_a_math_id, seeded.section_a_id)}


# --- Item 5: institution isolation, admin included ------------------------------------


async def test_admin_never_sees_another_institutions_rows(
    async_session: AsyncSession, seeded: _Fixture
) -> None:
    rows = await _run_scoped(
        async_session,
        sql="SELECT id FROM student_profiles",
        user_id=seeded.admin_user_id,
        role="admin",
        institution_id=seeded.institution_id,
    )
    ids = {row["id"] for row in rows}

    assert seeded.other_student_id not in ids
    assert seeded.student_a_math_id in ids  # sanity: still sees their own institution

"""The permission test matrix from docs/design/02, section 11a.

Each test here corresponds to a numbered rule in the spec. When a rule changes, change the
spec first and then this file -- these tests are the evidence behind the claim that
role-based access actually holds.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from education_platform.db.url import to_async_url, to_sync_url
from education_platform.modules.academics.models import GradeSubjectOffering, Subject
from education_platform.modules.auth.models import RoleName, StudentProfile, User, UserRole
from education_platform.modules.authorization.scope import scope_for
from education_platform.modules.insights.service import query_student_360, scope_predicate
from education_platform.modules.synthetic.generator import SchoolSpec, generate_school

# A deliberately small school: same shape, same planted narrative, fast enough for CI.
TEST_SPEC = SchoolSpec(sections_per_grade=2, students_per_section=3, term_weeks=2)


@dataclass(frozen=True)
class FakePrincipal:
    """Stands in for api.deps.Principal without needing an HTTP request."""

    user_id: UUID
    institution_id: UUID
    email: str
    roles: frozenset[str]
    student_profile_id: UUID | None
    status: str = "active"


@pytest.fixture()
def synthetic_db(clean_db: str) -> Iterator[str]:
    """A generated school in the shared Postgres test database."""
    engine = create_engine(to_sync_url(clean_db), pool_pre_ping=True)
    with Session(engine) as session:
        generate_school(session, TEST_SPEC)
        session.commit()
    engine.dispose()
    yield clean_db


@pytest_asyncio.fixture()
async def async_session(synthetic_db: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(to_async_url(synthetic_db), pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _principal_for(session: AsyncSession, email: str) -> FakePrincipal:
    user = await session.scalar(select(User).where(User.email == email.lower()))
    assert user is not None, f"no user {email}"
    roles = await session.scalars(select(UserRole.role).where(UserRole.user_id == user.id))
    profile_id = await session.scalar(
        select(StudentProfile.id).where(StudentProfile.user_id == user.id)
    )
    return FakePrincipal(
        user_id=user.id,
        institution_id=user.institution_id,
        email=user.email,
        roles=frozenset(role.value for role in roles),
        student_profile_id=profile_id,
    )


async def _aisha(session: AsyncSession) -> FakePrincipal:
    profile = await session.scalar(
        select(StudentProfile).where(StudentProfile.full_name == "Aisha Rahman")
    )
    assert profile is not None
    user = await session.get(User, profile.user_id)
    assert user is not None
    return await _principal_for(session, user.email)


# --------------------------------------------------------------------- rules


@pytest.mark.asyncio
async def test_rule_01_administrator_is_unrestricted_within_their_institution(
    async_session: AsyncSession,
) -> None:
    principal = await _principal_for(async_session, "fatima.almansouri@alnoor.school")
    scope = await scope_for(async_session, principal)
    assert scope.unrestricted is True
    assert scope.institution_id == principal.institution_id


@pytest.mark.asyncio
async def test_rule_02_teacher_scope_is_offering_section_pairs_not_a_grade(
    async_session: AsyncSession,
) -> None:
    principal = await _principal_for(async_session, "meera.krishnan@alnoor.school")
    scope = await scope_for(async_session, principal)
    assert scope.unrestricted is False
    # Three assignments: Grade 8 Maths x2 sections, Grade 9 Science x1.
    assert len(scope.offering_sections) == 3
    assert len(scope.offering_ids) == 2


@pytest.mark.asyncio
async def test_rule_03_teacher_of_two_subjects_cannot_cross_into_the_third(
    async_session: AsyncSession,
) -> None:
    """The case the whole design turns on: same grade, different subject, still refused."""
    principal = await _principal_for(async_session, "meera.krishnan@alnoor.school")
    scope = await scope_for(async_session, principal)

    maths = await async_session.scalar(select(Subject).where(Subject.code == "MATH"))
    assert maths is not None
    other_grade_maths = await async_session.scalar(
        select(GradeSubjectOffering.id).where(
            GradeSubjectOffering.subject_id == maths.id,
            GradeSubjectOffering.id.notin_(scope.offering_ids),
        )
    )
    assert other_grade_maths is not None
    assert scope.allows_offering(other_grade_maths) is False


@pytest.mark.asyncio
async def test_rule_04_student_scope_is_exactly_themselves(async_session: AsyncSession) -> None:
    principal = await _aisha(async_session)
    scope = await scope_for(async_session, principal)
    assert scope.unrestricted is False
    assert scope.student_ids == frozenset({principal.student_profile_id})


@pytest.mark.asyncio
async def test_rule_05_student_cannot_reach_a_classmate(async_session: AsyncSession) -> None:
    principal = await _aisha(async_session)
    scope = await scope_for(async_session, principal)
    classmate = await async_session.scalar(
        select(StudentProfile.id).where(StudentProfile.id != principal.student_profile_id)
    )
    assert classmate is not None
    assert scope.allows_student(classmate) is False


@pytest.mark.asyncio
async def test_rule_06_teacher_reaches_only_their_own_students(
    async_session: AsyncSession,
) -> None:
    principal = await _principal_for(async_session, "meera.krishnan@alnoor.school")
    scope = await scope_for(async_session, principal)

    total_students = await async_session.scalar(select(func.count()).select_from(StudentProfile))
    assert total_students is not None
    assert 0 < len(scope.student_ids) < int(total_students)


@pytest.mark.asyncio
async def test_rule_07_out_of_scope_query_returns_zero_rows_not_an_error(
    async_session: AsyncSession,
) -> None:
    """The behaviour that matters most: empty, never a message confirming data exists."""
    principal = await _principal_for(async_session, "meera.krishnan@alnoor.school")
    scope = await scope_for(async_session, principal)
    rows = await query_student_360(async_session, scope, grade="Grade 10")
    assert rows == []


@pytest.mark.asyncio
async def test_rule_08_student_reading_the_register_gets_exactly_their_own_rows(
    async_session: AsyncSession,
) -> None:
    principal = await _aisha(async_session)
    scope = await scope_for(async_session, principal)
    rows = await query_student_360(async_session, scope)
    assert rows, "the planted student should have subject rows"
    assert {row.student_id for row in rows} == {principal.student_profile_id}


@pytest.mark.asyncio
async def test_rule_09_administrator_sees_more_than_any_teacher(
    async_session: AsyncSession,
) -> None:
    admin = await _principal_for(async_session, "fatima.almansouri@alnoor.school")
    teacher = await _principal_for(async_session, "meera.krishnan@alnoor.school")

    admin_rows = await query_student_360(
        async_session, await scope_for(async_session, admin), limit=500
    )
    teacher_rows = await query_student_360(
        async_session, await scope_for(async_session, teacher), limit=500
    )
    assert len(admin_rows) > len(teacher_rows) > 0


@pytest.mark.asyncio
async def test_rule_10_principal_with_no_assignments_reaches_nothing(
    async_session: AsyncSession,
) -> None:
    """A provisioned account with a role but no assignments must be closed, not open."""
    admin = await _principal_for(async_session, "fatima.almansouri@alnoor.school")
    orphan = FakePrincipal(
        user_id=admin.user_id,
        institution_id=admin.institution_id,
        email="orphan@alnoor.school",
        roles=frozenset({RoleName.TEACHER.value}),
        student_profile_id=None,
    )
    scope = await scope_for(async_session, orphan)
    assert scope.is_empty is True
    assert await query_student_360(async_session, scope) == []


@pytest.mark.asyncio
async def test_rule_11_empty_scope_compiles_to_a_false_predicate(
    async_session: AsyncSession,
) -> None:
    admin = await _principal_for(async_session, "fatima.almansouri@alnoor.school")
    orphan = FakePrincipal(
        user_id=admin.user_id,
        institution_id=admin.institution_id,
        email="orphan@alnoor.school",
        roles=frozenset({RoleName.TEACHER.value}),
        student_profile_id=None,
    )
    scope = await scope_for(async_session, orphan)
    compiled = scope_predicate(scope).compile(compile_kwargs={"literal_binds": True})
    assert str(compiled).lower() in {"false", "0 = 1"}


@pytest.mark.asyncio
async def test_rule_12_every_scope_clause_pins_the_institution(
    async_session: AsyncSession,
) -> None:
    """Tenant isolation is never optional, including for administrators."""
    for email in ("fatima.almansouri@alnoor.school", "meera.krishnan@alnoor.school"):
        principal = await _principal_for(async_session, email)
        scope = await scope_for(async_session, principal)
        compiled = scope_predicate(scope).compile()
        assert "institution_id" in str(compiled)
        assert principal.institution_id in compiled.params.values()


@pytest.mark.asyncio
async def test_rule_13_reads_are_row_limited(async_session: AsyncSession) -> None:
    admin = await _principal_for(async_session, "fatima.almansouri@alnoor.school")
    scope = await scope_for(async_session, admin)
    rows = await query_student_360(async_session, scope, limit=3)
    assert len(rows) <= 3


MEERA_TEACHES = {("Grade 8", "Mathematics"), ("Grade 9", "Science")}


@pytest.mark.asyncio
async def test_rule_14_teacher_reads_only_the_subjects_they_teach(
    async_session: AsyncSession,
) -> None:
    """Found by Aushak in review.

    Narrowing to the teacher's *students* is not narrowing to the teacher's *data*. Each of
    Meera's Grade 8 Mathematics pupils also has Science, English, Arabic and Social Studies
    rows in the register, and a student-id filter returned every one of them.
    """
    teacher = await _principal_for(async_session, "meera.krishnan@alnoor.school")
    scope = await scope_for(async_session, teacher)
    rows = await query_student_360(async_session, scope, limit=500)

    assert rows, "she must still see the assignments she does have"
    assert {(row.grade, row.subject) for row in rows} == MEERA_TEACHES

    # The assertion above only has teeth if those pupils really do study other subjects.
    admin = await _principal_for(async_session, "fatima.almansouri@alnoor.school")
    everything = await query_student_360(
        async_session, await scope_for(async_session, admin), limit=500
    )
    her_pupils = {row.student_id for row in rows}
    withheld = [
        row
        for row in everything
        if row.student_id in her_pupils and (row.grade, row.subject) not in MEERA_TEACHES
    ]
    assert withheld, "her pupils must study subjects she does not teach, or this proves nothing"


@pytest.mark.asyncio
async def test_rule_15_student_is_not_widened_by_the_subjects_they_are_enrolled_in(
    async_session: AsyncSession,
) -> None:
    """Guards the wrong fix as firmly as rule 14 guards the bug.

    Filtering on offering/section pairs alone would hand a student every classmate sitting
    in the same subject, because a student's enrolment produces the very same pairs. Only
    pairs the principal *teaches* may widen a read past their own record.
    """
    student = await _aisha(async_session)
    scope = await scope_for(async_session, student)

    assert scope.enrolled_offering_sections, "the fixture student must be enrolled in subjects"
    assert scope.taught_offering_sections == frozenset(), "a student teaches nothing"

    rows = await query_student_360(async_session, scope, limit=500)
    assert {row.student_id for row in rows} == {student.student_profile_id}
    assert len(rows) == len(scope.enrolled_offering_sections), "one row per subject, all her own"

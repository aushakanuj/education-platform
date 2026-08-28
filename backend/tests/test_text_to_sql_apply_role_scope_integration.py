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

import education_platform.modules.text_to_sql.graph as graph_module
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
    Subtopic,
    TeachingAssignment,
    TeachingAssignmentStatus,
    Topic,
)
from education_platform.modules.assessments.models import (
    AttemptAnswer,
    CommonMasteryQuiz,
    Question,
    QuestionType,
    QuestionVersion,
    QuestionVersionStatus,
    QuizAttempt,
    QuizAttemptStatus,
    QuizResultReleaseMode,
    QuizScope,
    QuizVersion,
    QuizVersionStatus,
)
from education_platform.modules.attendance.models import AttendanceRecord, AttendanceStatus
from education_platform.modules.auth.models import (
    Institution,
    RoleName,
    StudentProfile,
    User,
    UserRole,
)
from education_platform.modules.authorization.predicate import ScopeColumns, scope_predicate_for
from education_platform.modules.authorization.scope import scope_for
from education_platform.modules.insights.models import student_360
from education_platform.modules.insights.service import scope_predicate
from education_platform.modules.text_to_sql.graph import build_text_to_sql_graph
from education_platform.modules.text_to_sql.nodes.apply_role_scope import apply_role_scope
from education_platform.modules.text_to_sql.state import (
    ROLE_VIOLATION,
    TextToSQLState,
    error_category,
)


@dataclass(frozen=True)
class _Fixture:
    institution_id: UUID
    other_institution_id: UUID

    teacher_user_id: UUID
    admin_user_id: UUID

    # Second teacher, Math *all sections* (section_id NULL) — contrasts with the primary
    # teacher's Math/8A-only grant for the Q3 regression: same phrased question, two
    # teachers, two different correctly-scoped counts.
    teacher2_user_id: UUID

    section_a_id: UUID  # "8A" — the teacher's Math assignment names this section only
    section_b_id: UUID  # "8B" — outside the Math assignment; inside the NULL-section one

    # Logged-in student in Math/8A: reached by the teacher's *specific*-section grant.
    student_a_math_id: UUID
    student_a_math_user_id: UUID

    # Logged-in student in Math/8B: same subject, wrong section — must be excluded.
    student_b_math_id: UUID

    # student_a_math's/student_b_math's own StudentSubjectEnrollment row (Math), for the
    # Q3-shape and student_subject_enrollments tests.
    enrollment_a_math_id: UUID
    enrollment_b_math_id: UUID

    # A quiz attempt (+ its one attempt_answer) per Math student, for attempt_answers.
    attempt_a_math_id: UUID
    answer_a_math_id: UUID
    attempt_b_math_id: UUID
    answer_b_math_id: UUID

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
    teacher2 = User(
        institution_id=inst1.id,
        email="teacher2@ars-integration.school",
        full_name="Teacher Two",
        password_hash="unused",
    )
    session.add_all([teacher, admin, teacher2])
    session.flush()
    session.add_all(
        [
            UserRole(user_id=teacher.id, role=RoleName.TEACHER),
            UserRole(user_id=admin.id, role=RoleName.ADMINISTRATOR),
            UserRole(user_id=teacher2.id, role=RoleName.TEACHER),
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
    # Second teacher: Math, *all* sections (section_id NULL) — reaches both 8A and 8B,
    # unlike the primary teacher's 8A-only Math grant.
    session.add(
        TeachingAssignment(
            teacher_user_id=teacher2.id,
            academic_period_id=period.id,
            grade_subject_offering_id=offering_math.id,
            section_id=None,
            status=TeachingAssignmentStatus.ACTIVE,
        )
    )

    def _enroll_student(
        *, identifier: str, section: Section, offering: GradeSubjectOffering, with_login: bool
    ) -> tuple[StudentProfile, StudentSubjectEnrollment]:
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
        subject_enrollment = StudentSubjectEnrollment(
            student_id=profile.id,
            grade_enrollment_id=grade_enrollment.id,
            grade_subject_offering_id=offering.id,
            status=EnrollmentStatus.ACTIVE,
        )
        session.add(subject_enrollment)
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
        return profile, subject_enrollment

    student_a_math, enrollment_a_math = _enroll_student(
        identifier="stu-a-math", section=section_a, offering=offering_math, with_login=True
    )
    student_b_math, enrollment_b_math = _enroll_student(
        identifier="stu-b-math", section=section_b, offering=offering_math, with_login=True
    )
    student_a_science, _enrollment_a_science = _enroll_student(
        identifier="stu-a-science", section=section_a, offering=offering_science, with_login=True
    )
    student_b_science_provisioned, _enrollment_b_science = _enroll_student(
        identifier="stu-b-science-noauth",
        section=section_b,
        offering=offering_science,
        with_login=False,
    )

    # Quiz-attempt chain, for attempt_answers: Question -> QuestionVersion (curriculum
    # content, deliberately out of scope for this fix) feed into real quiz_attempts /
    # attempt_answers rows (in scope), one per Math student, so the teacher/student row
    # predicates on the newly-scoped attempt_answers table can be proven against live data.
    topic = Topic(grade_subject_offering_id=offering_math.id, name="Algebra", slug="algebra", sequence=1)
    session.add(topic)
    session.flush()
    subtopic = Subtopic(topic_id=topic.id, name="Linear Equations", slug="linear-eq", sequence=1)
    session.add(subtopic)
    session.flush()
    question = Question(subtopic_id=subtopic.id, code="Q1")
    session.add(question)
    session.flush()
    question_version = QuestionVersion(
        question_id=question.id,
        version_number=1,
        prompt="Solve for x: x + 1 = 2",
        question_type=QuestionType.NUMERIC,
        lifecycle_status=QuestionVersionStatus.PUBLISHED,
    )
    session.add(question_version)
    session.flush()
    quiz = CommonMasteryQuiz(
        subtopic_id=subtopic.id, quiz_scope=QuizScope.SUBTOPIC_MASTERY, title="Linear Equations Quiz"
    )
    session.add(quiz)
    session.flush()
    quiz_version = QuizVersion(
        quiz_id=quiz.id,
        version_number=1,
        lifecycle_status=QuizVersionStatus.RELEASED,
        result_release_mode=QuizResultReleaseMode.IMMEDIATE,
    )
    session.add(quiz_version)
    session.flush()

    def _record_attempt(
        *, student: StudentProfile, enrollment: StudentSubjectEnrollment
    ) -> tuple[UUID, UUID]:
        attempt = QuizAttempt(
            student_id=student.id,
            student_subject_enrollment_id=enrollment.id,
            quiz_version_id=quiz_version.id,
            attempt_number=1,
            status=QuizAttemptStatus.SCORED,
        )
        session.add(attempt)
        session.flush()
        answer = AttemptAnswer(
            attempt_id=attempt.id,
            question_version_id=question_version.id,
            selected_numeric=1,
            is_correct=True,
        )
        session.add(answer)
        session.flush()
        return attempt.id, answer.id

    attempt_a_math_id, answer_a_math_id = _record_attempt(
        student=student_a_math, enrollment=enrollment_a_math
    )
    attempt_b_math_id, answer_b_math_id = _record_attempt(
        student=student_b_math, enrollment=enrollment_b_math
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
        teacher2_user_id=teacher2.id,
        section_a_id=section_a.id,
        section_b_id=section_b.id,
        student_a_math_id=student_a_math.id,
        student_a_math_user_id=student_a_math.user_id,
        student_b_math_id=student_b_math.id,
        enrollment_a_math_id=enrollment_a_math.id,
        enrollment_b_math_id=enrollment_b_math.id,
        attempt_a_math_id=attempt_a_math_id,
        answer_a_math_id=answer_a_math_id,
        attempt_b_math_id=attempt_b_math_id,
        answer_b_math_id=answer_b_math_id,
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


# --- Priority fix: Q3 regression — student_subject_enrollments/grade_subject_offerings
# --- routed entirely outside the original 5 sensitive tables --------------------------


async def test_q3_shape_no_longer_returns_school_wide_count(
    async_session: AsyncSession, seeded: _Fixture
) -> None:
    """The exact shape of the live query that leaked: "how many students enrolled for
    maths subject for grade 8", routed entirely through student_subject_enrollments /
    grade_subject_offerings / subjects / period_grades — none of which were in the
    original SCOPE_SENSITIVE_TABLES list. Before this fix this returned a school-wide
    count (2, in this fixture: student_a_math + student_b_math); after it, the primary
    teacher's Math/8A-only grant must narrow it to 1.
    """
    sql = (
        "SELECT COUNT(DISTINCT se.student_id) AS student_count "
        "FROM student_subject_enrollments se "
        "JOIN grade_subject_offerings gso ON se.grade_subject_offering_id = gso.id "
        "JOIN subjects s ON gso.subject_id = s.id "
        "JOIN period_grades pg ON gso.period_grade_id = pg.id "
        "WHERE s.name = 'Mathematics' AND se.status = 'active'"
    )
    rows = await _run_scoped(
        async_session,
        sql=sql,
        user_id=seeded.teacher_user_id,
        role="teacher",
        institution_id=seeded.institution_id,
    )
    assert rows[0]["student_count"] == 1  # student_a_math only — 8A, not 8B


async def test_q3_shape_two_teachers_get_different_correctly_scoped_counts(
    async_session: AsyncSession, seeded: _Fixture
) -> None:
    """Same phrased question, two teachers, two different counts — the primary teacher's
    Math/8A-only grant sees 1 student; the second teacher's Math/all-sections grant sees
    both (2). Neither is the unscoped school-wide total that used to be returned
    regardless of which teacher asked.
    """
    sql = (
        "SELECT COUNT(DISTINCT se.student_id) AS student_count "
        "FROM student_subject_enrollments se "
        "JOIN grade_subject_offerings gso ON se.grade_subject_offering_id = gso.id "
        "JOIN subjects s ON gso.subject_id = s.id "
        "WHERE s.name = 'Mathematics' AND se.status = 'active'"
    )
    rows_teacher1 = await _run_scoped(
        async_session,
        sql=sql,
        user_id=seeded.teacher_user_id,
        role="teacher",
        institution_id=seeded.institution_id,
    )
    rows_teacher2 = await _run_scoped(
        async_session,
        sql=sql,
        user_id=seeded.teacher2_user_id,
        role="teacher",
        institution_id=seeded.institution_id,
    )
    assert rows_teacher1[0]["student_count"] == 1
    assert rows_teacher2[0]["student_count"] == 2
    assert rows_teacher1[0]["student_count"] != rows_teacher2[0]["student_count"]


async def test_student_subject_enrollments_cross_institution_isolation(
    async_session: AsyncSession, seeded: _Fixture
) -> None:
    rows = await _run_scoped(
        async_session,
        sql="SELECT student_id FROM student_subject_enrollments",
        user_id=seeded.admin_user_id,
        role="admin",
        institution_id=seeded.institution_id,
    )
    ids = {row["student_id"] for row in rows}
    assert seeded.other_student_id not in ids
    assert seeded.student_a_math_id in ids


# --- Priority fix: student_grade_enrollments (same class of gap, one level up) --------


async def test_student_grade_enrollments_all_sections_grant_reaches_whole_grade(
    async_session: AsyncSession, seeded: _Fixture
) -> None:
    # student_grade_enrollments carries no subject dimension (it's the whole-grade
    # enrollment, not a per-subject one) -- an all-sections (section_id NULL) teaching
    # assignment for *any* subject in that grade correctly grants visibility into every
    # student's grade-level row in that grade, not just the students of that one subject.
    # Both teacher 1 (Science, all sections) and teacher 2 (Math, all sections) hold such
    # a grant here, so both see all four students -- this is the predicate matching
    # student_grade_enrollments' actual (coarser) granularity, not a scoping gap.
    all_students = {
        seeded.student_a_math_id,
        seeded.student_b_math_id,
        seeded.student_a_science_id,
        seeded.student_b_science_provisioned_id,
    }
    for teacher_id in (seeded.teacher_user_id, seeded.teacher2_user_id):
        rows = await _run_scoped(
            async_session,
            sql="SELECT student_id FROM student_grade_enrollments",
            user_id=teacher_id,
            role="teacher",
            institution_id=seeded.institution_id,
        )
        assert {row["student_id"] for row in rows} == all_students


async def test_student_grade_enrollments_student_sees_only_own_row(
    async_session: AsyncSession, seeded: _Fixture
) -> None:
    rows = await _run_scoped(
        async_session,
        sql="SELECT student_id FROM student_grade_enrollments",
        user_id=seeded.student_a_math_user_id,
        role="student",
        institution_id=seeded.institution_id,
    )
    assert {row["student_id"] for row in rows} == {seeded.student_a_math_id}


# --- Priority fix: attempt_answers (individual quiz-answer content, no direct
# --- student_id/institution_id of its own -- resolved via quiz_attempts) --------------


async def test_attempt_answers_teacher_scoping_specific_section_excludes_other_section(
    async_session: AsyncSession, seeded: _Fixture
) -> None:
    rows = await _run_scoped(
        async_session,
        sql="SELECT id FROM attempt_answers",
        user_id=seeded.teacher_user_id,
        role="teacher",
        institution_id=seeded.institution_id,
    )
    ids = {row["id"] for row in rows}
    assert seeded.answer_a_math_id in ids  # Math/8A -- teacher 1's specific grant
    assert seeded.answer_b_math_id not in ids  # Math/8B -- outside that grant


async def test_attempt_answers_teacher2_all_sections_sees_both(
    async_session: AsyncSession, seeded: _Fixture
) -> None:
    rows = await _run_scoped(
        async_session,
        sql="SELECT id FROM attempt_answers",
        user_id=seeded.teacher2_user_id,
        role="teacher",
        institution_id=seeded.institution_id,
    )
    ids = {row["id"] for row in rows}
    assert ids == {seeded.answer_a_math_id, seeded.answer_b_math_id}


async def test_attempt_answers_student_sees_only_own_answers(
    async_session: AsyncSession, seeded: _Fixture
) -> None:
    rows = await _run_scoped(
        async_session,
        sql="SELECT id FROM attempt_answers",
        user_id=seeded.student_a_math_user_id,
        role="student",
        institution_id=seeded.institution_id,
    )
    assert {row["id"] for row in rows} == {seeded.answer_a_math_id}


# --- Priority fix: INSTITUTION_SCOPED_TABLES (not individually restricted, but must
# --- not leak across tenants) ----------------------------------------------------------


async def test_users_table_institution_pin_hides_other_institutions_users(
    async_session: AsyncSession, seeded: _Fixture
) -> None:
    # Add a user at the other institution so this test has something to prove hidden.
    other_inst_user = User(
        institution_id=seeded.other_institution_id,
        email="other-inst-user@ars-integration.school",
        full_name="Other Institution User",
        password_hash="unused",
    )
    async_session.add(other_inst_user)
    await async_session.flush()

    for role in ("admin", "teacher", "student"):
        rows = await _run_scoped(
            async_session,
            sql="SELECT id, email FROM users",
            user_id=seeded.teacher_user_id,
            role=role,
            institution_id=seeded.institution_id,
        )
        emails = {row["email"] for row in rows}
        assert "other-inst-user@ars-integration.school" not in emails
        assert "teacher@ars-integration.school" in emails


async def test_subjects_and_grades_pinned_to_institution_for_every_role(
    async_session: AsyncSession, seeded: _Fixture
) -> None:
    other_subject = Subject(
        institution_id=seeded.other_institution_id, name="Other Institution Subject", code="OTH"
    )
    async_session.add(other_subject)
    await async_session.flush()

    for role in ("admin", "teacher", "student"):
        rows = await _run_scoped(
            async_session,
            sql="SELECT name FROM subjects",
            user_id=seeded.teacher_user_id,
            role=role,
            institution_id=seeded.institution_id,
        )
        names = {row["name"] for row in rows}
        assert "Other Institution Subject" not in names
        assert "Mathematics" in names


async def test_teaching_assignments_institution_pin_not_self_only(
    async_session: AsyncSession, seeded: _Fixture
) -> None:
    # Deliberate scope of this pass: teaching_assignments gets the institution pin, not a
    # self-only row predicate -- teacher 1 sees teacher 2's assignment rows too, just not
    # another institution's.
    rows = await _run_scoped(
        async_session,
        sql="SELECT teacher_user_id FROM teaching_assignments",
        user_id=seeded.teacher_user_id,
        role="teacher",
        institution_id=seeded.institution_id,
    )
    teacher_ids = {row["teacher_user_id"] for row in rows}
    assert seeded.teacher_user_id in teacher_ids
    assert seeded.teacher2_user_id in teacher_ids


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


async def test_cross_check_admin_scope_matches_scope_predicate_across_institutions(
    async_session: AsyncSession, seeded: _Fixture
) -> None:
    """`scope_predicate()`/`scope_predicate_for()` runs `institution == scope.institution_id`
    unconditionally, even for `scope.unrestricted` admin scopes (that "unconditional even
    for unrestricted" behaviour is the change PR #128 made) -- confirm our node's own
    institution predicate agrees with it directly, not just that our node alone stays
    within one institution.

    `student_profiles` carries no `grade_subject_offering_id`/`section_id` of its own, so
    those two `ScopeColumns` slots are filled with a column that is never actually read:
    `scope_predicate_for` returns right after the institution check for an unrestricted
    scope, before either slot is touched. This is exactly the gap Q2 identifies -- no real
    `ScopeColumns` mapping exists yet for `student_profiles`, only enough of one to prove
    the admin/institution rule for this one query shape.
    """
    principal = _FakePrincipal(
        user_id=seeded.admin_user_id,
        institution_id=seeded.institution_id,
        email="admin@ars-integration.school",
        roles=frozenset({RoleName.ADMINISTRATOR.value}),
        student_profile_id=None,
    )
    scope = await scope_for(async_session, principal)
    table = StudentProfile.__table__
    columns = ScopeColumns(
        institution_id=table.c.institution_id,
        student_id=table.c.id,
        grade_subject_offering_id=table.c.id,
        section_id=table.c.id,
    )
    predicate_rows = (
        await async_session.execute(
            select(StudentProfile.id).where(scope_predicate_for(scope, columns))
        )
    ).all()
    predicate_ids = {row.id for row in predicate_rows}

    node_rows = await _run_scoped(
        async_session,
        sql="SELECT id FROM student_profiles",
        user_id=seeded.admin_user_id,
        role="admin",
        institution_id=seeded.institution_id,
    )
    node_ids = {row["id"] for row in node_rows}

    assert predicate_ids == node_ids
    assert seeded.other_student_id not in predicate_ids
    assert seeded.student_a_math_id in predicate_ids


# --- Fix (Finding 2): self-reference sentinel, through the full compiled graph --------


async def test_what_subject_do_i_teach_returns_real_answer_through_full_graph(
    monkeypatch: pytest.MonkeyPatch, seeded: _Fixture
) -> None:
    """The exact observed defect: "what subject do I teach" resolves through
    teaching_assignments (INSTITUTION_SCOPED_TABLES -- institution pin only, no
    self-narrowing), so the model needs a genuine self-reference filter it has no real
    value for. Before this fix it fabricated a placeholder that matched nothing; now the
    prompt's fixed sentinel gets resolved to the real teacher_user_id and the query
    returns real data -- the seeded teacher genuinely teaches Math and Science.
    """
    sentinel_sql = (
        "SELECT DISTINCT s.name AS subject_name FROM teaching_assignments ta "
        "JOIN grade_subject_offerings gso ON gso.id = ta.grade_subject_offering_id "
        "JOIN subjects s ON s.id = gso.subject_id "
        "WHERE ta.teacher_user_id = '__CURRENT_USER_ID__' AND ta.status = 'active'"
    )

    async def _fake_generate_sql(state: TextToSQLState) -> TextToSQLState:
        return {**state, "generated_sql": sentinel_sql, "error": None}

    monkeypatch.setattr(graph_module, "generate_sql", _fake_generate_sql)
    graph = build_text_to_sql_graph()
    initial: TextToSQLState = {
        "question": "what subject do I teach?",
        "user_id": str(seeded.teacher_user_id),
        "user_role": "teacher",
        "institution_id": str(seeded.institution_id),
        "schema_context": "",
        "generated_sql": None,
        "validated_sql": None,
        "retry_count": 0,
        "query_result": None,
        "result_row_count": None,
        "natural_answer": None,
        "confidence": None,
        "provenance": None,
        "error": None,
        "audit_entry": None,
    }
    result = await graph.ainvoke(initial, config={"recursion_limit": 15})

    assert result["error"] is None
    # Real, non-empty, correct answer -- not the confidently-wrong empty result the
    # fabricated-placeholder defect produced.
    subject_names = {row["subject_name"] for row in result["query_result"]}
    assert subject_names == {"Mathematics", "Science"}
    assert result["result_row_count"] == 2

    # Assert on content, not just the final answer: a lucky-correct answer over a still-
    # fabricated literal would be a false pass. generated_sql (pre-resolution) must carry
    # the fixed token, never the real ID; validated_sql (post apply_role_scope) must carry
    # the real teacher's ID and must not still contain the sentinel or any fabricated
    # literal in its place.
    assert "__CURRENT_USER_ID__" in result["generated_sql"]
    assert str(seeded.teacher_user_id) not in result["generated_sql"]
    assert str(seeded.teacher_user_id) in result["validated_sql"]
    assert "__CURRENT_USER_ID__" not in result["validated_sql"]


async def test_question_without_self_reference_is_unaffected_through_full_graph(
    monkeypatch: pytest.MonkeyPatch, seeded: _Fixture
) -> None:
    # Confirms this fix doesn't overcorrect into requiring/expecting the sentinel where a
    # question never needed self-reference at all.
    async def _fake_generate_sql(state: TextToSQLState) -> TextToSQLState:
        return {**state, "generated_sql": "SELECT name FROM subjects", "error": None}

    monkeypatch.setattr(graph_module, "generate_sql", _fake_generate_sql)
    graph = build_text_to_sql_graph()
    initial: TextToSQLState = {
        "question": "what subjects exist in the school?",
        "user_id": str(seeded.teacher_user_id),
        "user_role": "teacher",
        "institution_id": str(seeded.institution_id),
        "schema_context": "",
        "generated_sql": None,
        "validated_sql": None,
        "retry_count": 0,
        "query_result": None,
        "result_row_count": None,
        "natural_answer": None,
        "confidence": None,
        "provenance": None,
        "error": None,
        "audit_entry": None,
    }
    result = await graph.ainvoke(initial, config={"recursion_limit": 15})

    assert result["error"] is None
    names = {row["name"] for row in result["query_result"]}
    assert names == {"Mathematics", "Science"}
    assert "__CURRENT_USER_ID__" not in result["validated_sql"]
    assert str(seeded.teacher_user_id) not in result["validated_sql"]


async def test_student_self_reference_also_resolves_through_full_graph(
    monkeypatch: pytest.MonkeyPatch, seeded: _Fixture
) -> None:
    # Step 0 finding: this gap is symmetric, not teacher-only -- a student asking "what's
    # my email" over `users` (also INSTITUTION_SCOPED_TABLES) needs the identical fix.
    async def _fake_generate_sql(state: TextToSQLState) -> TextToSQLState:
        return {
            **state,
            "generated_sql": "SELECT email FROM users WHERE id = '__CURRENT_USER_ID__'",
            "error": None,
        }

    monkeypatch.setattr(graph_module, "generate_sql", _fake_generate_sql)
    graph = build_text_to_sql_graph()
    initial: TextToSQLState = {
        "question": "what's my email address?",
        "user_id": str(seeded.student_a_math_user_id),
        "user_role": "student",
        "institution_id": str(seeded.institution_id),
        "schema_context": "",
        "generated_sql": None,
        "validated_sql": None,
        "retry_count": 0,
        "query_result": None,
        "result_row_count": None,
        "natural_answer": None,
        "confidence": None,
        "provenance": None,
        "error": None,
        "audit_entry": None,
    }
    result = await graph.ainvoke(initial, config={"recursion_limit": 15})

    assert result["error"] is None
    assert result["query_result"] == [{"email": "stu-a-math@ars-integration.school"}]
    assert str(seeded.student_a_math_user_id) in result["validated_sql"]
    assert "__CURRENT_USER_ID__" not in result["validated_sql"]


# --- Graph-level: ROLE_VIOLATION routes to honest_refusal, not the retry loop ----------
#
# Moved here from test_text_to_sql_apply_role_scope.py (deliberately DB-free): now that
# audit_log (Task 10) runs unconditionally at the end of every full graph invocation, any
# test exercising the *compiled graph* end to end needs a real database — this file
# already has it via `seeded`/`clean_db`.


async def test_role_violation_routes_to_honest_refusal_through_compiled_graph(
    monkeypatch: pytest.MonkeyPatch, seeded: _Fixture
) -> None:
    async def _fake_generate_sql(state: TextToSQLState) -> TextToSQLState:
        # Bypass the real LLM call: hand validate_sql a query that will pass validation
        # but that apply_role_scope must reject on blocklist grounds.
        return {**state, "generated_sql": "SELECT password_hash FROM users", "error": None}

    # graph.py did `from ...nodes import generate_sql`, binding its own module-level
    # name — patching the nodes submodule's attribute (like generate_sql's own test
    # file does) would not affect graph.py's already-bound reference; patch graph.py's
    # own name instead, which build_text_to_sql_graph() resolves at call time.
    monkeypatch.setattr(graph_module, "generate_sql", _fake_generate_sql)

    graph = build_text_to_sql_graph()
    initial: TextToSQLState = {
        "question": "irrelevant",
        "user_id": str(seeded.admin_user_id),
        "user_role": "admin",
        "institution_id": str(seeded.institution_id),
        "schema_context": "",
        "generated_sql": None,
        "validated_sql": None,
        "retry_count": 0,
        "query_result": None,
        "result_row_count": None,
        "natural_answer": None,
        "confidence": None,
        "provenance": None,
        "error": None,
        "audit_entry": None,
    }
    result = await graph.ainvoke(initial, config={"recursion_limit": 15})

    assert error_category(result["error"]) == ROLE_VIOLATION
    # Did not loop back into generate_sql's retry path: retry_count stayed at whatever
    # validate_sql left it at (0 — it succeeded first try), not incremented again.
    assert result["retry_count"] == 0

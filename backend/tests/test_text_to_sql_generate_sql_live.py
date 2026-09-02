"""Opt-in, real-LLM regression tests for generate_sql.py's prompt-guidance fixes.

Every other test in this suite monkeypatches generate_sql (or chat_completion directly)
specifically so results are deterministic and free to run in CI on every commit. These
tests deliberately do the opposite: they call the real OpenRouter model, through the real
compiled graph, against real seeded data — because the thing under test is a property of
the *prompt*, not of any code these other tests can exercise. A prompt instruction
("use DISTINCT when joining a table only to check existence") is a request to a
probabilistic system, not a guarantee; a single passing run proves the model *can*
comply, never that it reliably *does*. That distinction is exactly what a live eval run
surfaced for two of this module's own fixes (row 33's "students enrolled in my subject
offerings" and a `quiz_attempts`-existence question): DISTINCT compliance measured 10/10
across two different question shapes, but avoiding a routing through Roadmap-7A-deferred
tables measured 100% (10/10) for the exact previously-failing phrasings and only 60%
(3/5) for a same-intent, differently-phrased question — a real, quantified gap, not
theoretical. These tests exist to keep measuring that rate on demand, not to claim it's 100%.

**Not run by default.** Real API calls cost money and are inherently non-deterministic,
so this file is skipped unless `RUN_LIVE_LLM_TESTS=1` is set in the environment — run it
deliberately (`RUN_LIVE_LLM_TESTS=1 uv run pytest tests/test_text_to_sql_generate_sql_live.py -v`)
whenever generate_sql.py's prompt changes, on the same "before any change to generate_sql"
cadence the golden eval set's own "How to run" sheet already asks for.

**Reads a rate, not a boolean.** Every test here runs the same question several times
and reports how many attempts complied, then asserts a floor loose enough to catch a
real regression (the guidance stops working at all) without being flaky over ordinary
LLM variance. The exact floors are set from the compliance rates actually observed during
this investigation (documented above and in generate_sql.py's own docstring), not
invented targets — if a future run's true rate is lower than what's asserted here, that
is itself a real finding, not a flaky test to raise the threshold on and move past.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from uuid import UUID

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from education_platform.db.url import to_sync_url
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
    CommonMasteryQuiz,
    QuizAttempt,
    QuizAttemptStatus,
    QuizResultReleaseMode,
    QuizScope,
    QuizVersion,
    QuizVersionStatus,
)
from education_platform.modules.auth.models import (
    Institution,
    RoleName,
    StudentProfile,
    User,
    UserRole,
)
from education_platform.modules.text_to_sql.graph import build_text_to_sql_graph
from education_platform.modules.text_to_sql.state import TextToSQLState

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_LLM_TESTS") != "1",
    reason="live-LLM test: costs real API calls and is inherently non-deterministic; "
    "run explicitly with RUN_LIVE_LLM_TESTS=1 when generate_sql.py's prompt changes",
)

_DISTINCT_OR_EXISTS_COMPLIANCE_FLOOR = 0.8  # observed 10/10 (2 question shapes); leaves
# real slack below the observed rate rather than asserting the exact number seen once.
_DEFERRED_TABLE_AVOIDANCE_FLOOR = 0.5  # observed 100% (10/10) for the exact previously-
# failing phrasings, 60% (3/5) for a related-but-differently-phrased question -- the
# floor is set at the *weaker* observed rate, not the stronger one, so this test reflects
# the real, currently-measured floor rather than the best case.

_DEFERRED_TABLES = (
    "topics",
    "subtopics",
    "questions",
    "question_versions",
    "common_mastery_quizzes",
    "quiz_versions",
    "quiz_items",
    "quiz_material_bindings",
    "quiz_releases",
    "source_materials",
    "source_material_versions",
    "source_chunks",
    "question_options",
    "question_outcome_tags",
)


@dataclass(frozen=True)
class _Fixture:
    institution_id: UUID
    teacher_user_id: UUID
    admin_user_id: UUID


def _seed(session: Session) -> _Fixture:
    """Self-contained (no cross-file import — `tests/` isn't a package here): a teacher
    with two Math sections (8A, 8B) sharing one grade_subject_offering_id — the exact
    row-33 pattern this file's Fix 1 tests need — several students enrolled across both
    sections, and one real second quiz attempt for one student, so the quiz_attempts
    multi-row case (Fix 1's other affected table) has genuine duplicate-prone data to
    test against, not just a theoretical join shape.
    """
    inst = Institution(name="Live-LLM Test School", timezone="UTC")
    session.add(inst)
    session.flush()

    period = AcademicPeriod(
        institution_id=inst.id,
        name="Term 1",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 6, 30),
        status=AcademicPeriodStatus.ACTIVE,
    )
    grade = Grade(institution_id=inst.id, name="Grade 8")
    subject = Subject(institution_id=inst.id, name="Mathematics", code="MATH")
    session.add_all([period, grade, subject])
    session.flush()

    period_grade = PeriodGrade(academic_period_id=period.id, grade_id=grade.id)
    session.add(period_grade)
    session.flush()

    section_a = Section(period_grade_id=period_grade.id, name="8A")
    section_b = Section(period_grade_id=period_grade.id, name="8B")
    session.add_all([section_a, section_b])
    session.flush()

    offering = GradeSubjectOffering(period_grade_id=period_grade.id, subject_id=subject.id)
    session.add(offering)
    session.flush()

    teacher = User(
        institution_id=inst.id,
        email="teacher@live-llm-test.school",
        full_name="Teacher",
        password_hash="unused",
    )
    admin = User(
        institution_id=inst.id,
        email="admin@live-llm-test.school",
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

    # The row-33 pattern: two teaching_assignment rows, one per section, sharing one
    # grade_subject_offering_id.
    session.add_all(
        [
            TeachingAssignment(
                teacher_user_id=teacher.id,
                academic_period_id=period.id,
                grade_subject_offering_id=offering.id,
                section_id=section_a.id,
                status=TeachingAssignmentStatus.ACTIVE,
            ),
            TeachingAssignment(
                teacher_user_id=teacher.id,
                academic_period_id=period.id,
                grade_subject_offering_id=offering.id,
                section_id=section_b.id,
                status=TeachingAssignmentStatus.ACTIVE,
            ),
        ]
    )

    # Minimal quiz-identity chain for a real, gradeable quiz_attempts row.
    topic = Topic(grade_subject_offering_id=offering.id, name="Algebra", slug="algebra", sequence=1)
    session.add(topic)
    session.flush()
    subtopic = Subtopic(topic_id=topic.id, name="Linear Equations", slug="linear-eq", sequence=1)
    session.add(subtopic)
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

    def _enroll(identifier: str, section: Section) -> tuple[StudentProfile, StudentSubjectEnrollment]:
        user = User(
            institution_id=inst.id,
            email=f"{identifier}@live-llm-test.school",
            full_name=identifier,
            password_hash="unused",
        )
        session.add(user)
        session.flush()
        profile = StudentProfile(
            institution_id=inst.id,
            user_id=user.id,
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
        session.flush()
        return profile, subject_enrollment

    students = [_enroll(f"student-{i}-{section.name}", section) for i, section in
                enumerate([section_a, section_a, section_b, section_b])]

    # Real duplicate-prone quiz_attempts data: a second attempt (attempt_number=2) for
    # the first student, same quiz_version as their first attempt.
    first_student, first_enrollment = students[0]
    session.add(
        QuizAttempt(
            student_id=first_student.id,
            student_subject_enrollment_id=first_enrollment.id,
            quiz_version_id=quiz_version.id,
            attempt_number=1,
            status=QuizAttemptStatus.SCORED,
            score_percent="70.00",
            passed=True,
        )
    )
    session.flush()
    session.add(
        QuizAttempt(
            student_id=first_student.id,
            student_subject_enrollment_id=first_enrollment.id,
            quiz_version_id=quiz_version.id,
            attempt_number=2,
            status=QuizAttemptStatus.SCORED,
            score_percent="85.00",
            passed=True,
        )
    )
    for student, enrollment in students[1:]:
        session.add(
            QuizAttempt(
                student_id=student.id,
                student_subject_enrollment_id=enrollment.id,
                quiz_version_id=quiz_version.id,
                attempt_number=1,
                status=QuizAttemptStatus.SCORED,
                score_percent="60.00",
                passed=False,
            )
        )
    session.flush()

    return _Fixture(institution_id=inst.id, teacher_user_id=teacher.id, admin_user_id=admin.id)


@pytest.fixture()
def seeded(clean_db: str) -> Iterator[_Fixture]:
    engine = create_engine(to_sync_url(clean_db), pool_pre_ping=True)
    with Session(engine) as session:
        fixture = _seed(session)
        session.commit()
    engine.dispose()
    yield fixture


def _initial_state(fixture: _Fixture, question: str, *, role: str = "teacher") -> TextToSQLState:
    user_id = fixture.teacher_user_id if role == "teacher" else fixture.admin_user_id
    return {
        "question": question,
        "user_id": str(user_id),
        "user_role": role,
        "institution_id": str(fixture.institution_id),
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


async def _run(fixture: _Fixture, question: str) -> TextToSQLState:
    graph = build_text_to_sql_graph()
    return await graph.ainvoke(
        _initial_state(fixture, question), config={"recursion_limit": 15}
    )


def _mentions_deferred_table(sql: str | None) -> bool:
    if not sql:
        return False
    lowered = sql.lower()
    return any(table in lowered for table in _DEFERRED_TABLES)


# --- Fix 1: DISTINCT/EXISTS for multi-row-per-entity joins -----------------------------


async def test_teaching_assignments_join_uses_distinct_or_exists_across_repeated_runs(
    seeded: _Fixture,
) -> None:
    # The exact row-33 shape: this fixture's teacher has two teaching_assignment rows
    # (Math/8A, Math/8B) sharing one grade_subject_offering_id -- the real pattern that
    # produced 120 rows for 72 real students before this fix.
    question = "List the students enrolled in my subject offerings."
    runs = 5
    compliant = 0
    for _ in range(runs):
        result = await _run(seeded, question)
        sql = (result.get("generated_sql") or "").lower()
        if "distinct" in sql or "exists" in sql or "not in" in sql:
            compliant += 1

    rate = compliant / runs
    assert rate >= _DISTINCT_OR_EXISTS_COMPLIANCE_FLOOR, (
        f"DISTINCT/EXISTS compliance dropped to {compliant}/{runs} ({rate:.0%}) -- "
        f"below the {_DISTINCT_OR_EXISTS_COMPLIANCE_FLOOR:.0%} floor observed during "
        "the investigation this test encodes. Re-read generate_sql.py's prompt guidance "
        "for multi-row-per-entity joins; this is a real regression, not test flakiness."
    )


async def test_quiz_attempts_multi_attempt_join_uses_distinct_or_exists(
    seeded: _Fixture,
) -> None:
    # quiz_attempts has the identical structural risk for a different reason
    # (attempt_number, not sections) -- confirmed via the same live investigation, not
    # assumed just because generate_sql.py's prompt happens to name both tables.
    question = "How many of my students have attempted a quiz this term?"
    runs = 5
    distinct_or_exists = 0
    for _ in range(runs):
        result = await _run(seeded, question)
        if result.get("error"):
            continue  # a refusal (e.g. routed through a deferred table) proves nothing
            # about DISTINCT/EXISTS compliance either way -- only count real attempts.
        sql = (result.get("generated_sql") or "").lower()
        if "distinct" in sql or "exists" in sql or "not in" in sql:
            distinct_or_exists += 1

    rate = distinct_or_exists / runs
    assert rate >= _DISTINCT_OR_EXISTS_COMPLIANCE_FLOOR, (
        f"DISTINCT/EXISTS compliance on the quiz_attempts case dropped to "
        f"{distinct_or_exists}/{runs} ({rate:.0%}) -- below the "
        f"{_DISTINCT_OR_EXISTS_COMPLIANCE_FLOOR:.0%} floor observed during the "
        "investigation this test encodes."
    )


# --- Fix 4: avoid unnecessary deferred-curriculum-table routing ------------------------


async def test_avoids_deferred_tables_for_simple_subject_filtered_questions(
    seeded: _Fixture,
) -> None:
    # A family of structurally similar questions (subject/grade-filtered roster or count),
    # each answerable via subjects/quiz_attempts directly -- not just rows 6/8's exact
    # phrasing confirmed once. Each question runs 3 times; the floor is asserted on the
    # pooled rate across the whole family, matching how the investigation measured it.
    questions = [
        "Which of my students scored below 40% in Mathematics?",
        "Which of my students have not submitted any quiz attempts this term?",
        "How many of my students have attempted a quiz this term?",
    ]
    runs_per_question = 3
    total = 0
    avoided = 0
    for question in questions:
        for _ in range(runs_per_question):
            result = await _run(seeded, question)
            total += 1
            if not _mentions_deferred_table(result.get("generated_sql")):
                avoided += 1

    rate = avoided / total
    assert rate >= _DEFERRED_TABLE_AVOIDANCE_FLOOR, (
        f"Deferred-table avoidance dropped to {avoided}/{total} ({rate:.0%}) across "
        f"{len(questions)} structurally similar questions -- below the "
        f"{_DEFERRED_TABLE_AVOIDANCE_FLOOR:.0%} floor observed during the investigation "
        "this test encodes (see generate_sql.py's own docstring for the exact numbers)."
    )

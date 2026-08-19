"""Audit trail, attendance, the master register, and the synthetic school generator."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from education_platform.db.url import to_async_url, to_sync_url
from education_platform.modules.academics.models import Section, TeachingAssignment
from education_platform.modules.attendance.models import AttendanceRecord, AttendanceStatus
from education_platform.modules.audit.service import AuditAction, list_events, record_event
from education_platform.modules.auth.models import (
    AuditEvent,
    Institution,
    RoleName,
    StudentProfile,
    UserRole,
)
from education_platform.modules.insights.models import student_360
from education_platform.modules.synthetic.generator import (
    PLANTED_ATTENDANCE_RATE,
    PLANTED_STUDENT_NAME,
    SchoolSpec,
    generate_school,
)

TEST_SPEC = SchoolSpec(sections_per_grade=2, students_per_section=3, term_weeks=2)


@pytest.fixture()
def synthetic_session(clean_db: str) -> Iterator[Session]:
    """A generated school, with an open session on the same database."""
    engine = create_engine(to_sync_url(clean_db), pool_pre_ping=True)
    with Session(engine) as session:
        generate_school(session, TEST_SPEC)
        session.commit()
        yield session
    engine.dispose()


@pytest.fixture()
def sync_session(clean_db: str) -> Iterator[Session]:
    """An empty database with a sync session -- for tests that build their own rows."""
    engine = create_engine(to_sync_url(clean_db), pool_pre_ping=True)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest_asyncio.fixture()
async def async_session(clean_db: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(to_async_url(clean_db), pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session
    await engine.dispose()


# ------------------------------------------------------------------ generator


def test_generator_produces_a_school_with_teachers_and_sections(
    synthetic_session: Session,
) -> None:
    """Before this task the database had one student, no teachers and no sections."""
    students = synthetic_session.scalar(select(func.count()).select_from(StudentProfile))
    teachers = synthetic_session.scalar(
        select(func.count()).select_from(UserRole).where(UserRole.role == RoleName.TEACHER)
    )
    sections = synthetic_session.scalar(select(func.count()).select_from(Section))
    assignments = synthetic_session.scalar(select(func.count()).select_from(TeachingAssignment))

    assert students == len(TEST_SPEC.grades) * TEST_SPEC.sections_per_grade * 3
    assert teachers is not None and teachers > 0, "a teacher must be able to exist and log in"
    assert sections == len(TEST_SPEC.grades) * TEST_SPEC.sections_per_grade
    assert assignments is not None and assignments > 0


def test_generator_is_deterministic(sync_session: Session) -> None:
    """Same seed, same school -- so a demo can be reset to a known state."""
    first = generate_school(sync_session, TEST_SPEC)
    sync_session.commit()
    first_scores = sync_session.execute(
        select(student_360.c.student_identifier, student_360.c.mastery_percent).order_by(
            student_360.c.student_identifier, student_360.c.mastery_percent
        )
    ).all()

    second = generate_school(sync_session, TEST_SPEC)
    sync_session.commit()
    second_scores = sync_session.execute(
        select(student_360.c.student_identifier, student_360.c.mastery_percent).order_by(
            student_360.c.student_identifier, student_360.c.mastery_percent
        )
    ).all()

    assert first.students == second.students
    assert first_scores == second_scores


def test_regenerating_works_after_the_school_has_been_used(sync_session: Session) -> None:
    """Audit events reference users, so a naive wipe hits a foreign-key violation.

    Found by running the demo twice: the first run leaves audit rows behind, and the second
    generation could not delete the users they point at.
    """
    first = generate_school(sync_session, TEST_SPEC)
    sync_session.commit()

    # Simulate the school having been used: somebody read some data.
    sync_session.add(
        AuditEvent(
            institution_id=first.institution_id,
            actor_user_id=sync_session.scalar(select(StudentProfile.user_id).limit(1)),
            event_type="data.scoped_read",
            entity_type="insights.students",
            payload={"rows_returned": 5},
        )
    )
    sync_session.commit()

    second = generate_school(sync_session, TEST_SPEC)
    sync_session.commit()
    assert second.students == first.students


def test_planted_declining_student_is_actually_declining(synthetic_session: Session) -> None:
    """A random generator would not produce this, and the demo depends on it."""
    row = synthetic_session.execute(
        select(student_360.c.mastery_percent, student_360.c.attendance_percent).where(
            student_360.c.full_name == PLANTED_STUDENT_NAME,
            student_360.c.subject == "Mathematics",
        )
    ).one()
    mastery, attendance = float(row[0]), float(row[1])
    assert mastery < 60, "the planted student must read as struggling"
    assert attendance < 75, "and must sit below the exam-eligibility threshold"


def test_planted_student_name_is_unique_across_the_school(synthetic_session: Session) -> None:
    """Both halves of the planted name are also in the random pools.

    A second student of the same name makes the demo ambiguous and breaks any query that
    looks the planted student up by name.
    """
    matches = synthetic_session.scalar(
        select(func.count())
        .select_from(StudentProfile)
        .where(StudentProfile.full_name == PLANTED_STUDENT_NAME)
    )
    assert matches == 1


def test_attendance_percentages_are_exact_not_sampled(synthetic_session: Session) -> None:
    """Coin-flipping attendance per day once put the planted student above the threshold.

    Fixing the count rather than sampling it keeps the narrative true on every run. The
    expected value is derived from the spec rather than hard-coded, because the achievable
    precision depends on how many school days the term has.
    """
    school_days = TEST_SPEC.term_weeks * 5
    expected = round(school_days * PLANTED_ATTENDANCE_RATE) / school_days * 100

    attendance = synthetic_session.scalar(
        select(student_360.c.attendance_percent)
        .where(student_360.c.full_name == PLANTED_STUDENT_NAME)
        .limit(1)
    )
    assert float(attendance) == pytest.approx(expected, abs=0.01), "exact, not sampled"
    assert float(attendance) < 75, "and still below the eligibility threshold"


def test_planted_section_gap_is_visible(synthetic_session: Session) -> None:
    rows = synthetic_session.execute(
        select(student_360.c.section, func.avg(student_360.c.mastery_percent))
        .where(student_360.c.grade == "Grade 8", student_360.c.subject == "Mathematics")
        .group_by(student_360.c.section)
        .order_by(student_360.c.section)
    ).all()
    assert len(rows) == 2
    section_a, section_b = float(rows[0][1]), float(rows[1][1])
    assert section_b > section_a, "section B should out-perform section A on the planted topic"


# ------------------------------------------------------------- master register


def test_student_360_has_one_row_per_student_per_subject(synthetic_session: Session) -> None:
    duplicates = synthetic_session.execute(
        text(
            "SELECT COUNT(*) FROM ("
            "  SELECT student_id, subject, academic_period_id FROM student_360"
            "  GROUP BY student_id, subject, academic_period_id HAVING COUNT(*) > 1"
            ") AS dupes"
        )
    ).scalar()
    assert duplicates == 0


def test_student_360_carries_the_columns_the_scope_filter_needs(
    synthetic_session: Session,
) -> None:
    """Without these the permission boundary cannot be applied to analytics at all."""
    columns = {
        row[0]
        for row in synthetic_session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'student_360'"
            )
        ).all()
    }
    for required in ("institution_id", "student_id", "section_id", "subject", "grade"):
        assert required in columns


def test_student_360_attendance_matches_the_underlying_records(
    synthetic_session: Session,
) -> None:
    row = synthetic_session.execute(
        select(
            student_360.c.student_id,
            student_360.c.days_present,
            student_360.c.days_counted,
            student_360.c.attendance_percent,
        )
        .where(student_360.c.days_counted > 0)
        .limit(1)
    ).one()
    student_id, present, counted, percent = row
    actual_present = synthetic_session.scalar(
        select(func.count())
        .select_from(AttendanceRecord)
        .where(
            AttendanceRecord.student_id == student_id,
            AttendanceRecord.status.in_([AttendanceStatus.PRESENT, AttendanceStatus.LATE]),
            AttendanceRecord.grade_subject_offering_id.is_(None),
        )
    )
    assert int(present) == int(actual_present)
    assert round(present * 100.0 / counted, 2) == pytest.approx(float(percent), abs=0.01)


# --------------------------------------------------------------------- audit


@pytest.mark.asyncio
async def test_audit_events_are_written_and_read_back(async_session: AsyncSession) -> None:
    """The table existed from day one with zero writes; this is the first one."""
    institution = Institution(name="Audit Test School")
    async_session.add(institution)
    await async_session.flush()

    await record_event(
        async_session,
        institution_id=institution.id,
        event_type=AuditAction.ASK_DATA,
        entity_type="insights.students",
        payload={"question": "how many are below 40%", "rows_returned": 3},
    )
    await async_session.commit()

    events = await list_events(async_session, institution_id=institution.id)
    assert len(events) == 1
    assert events[0].event_type == "data.ask"
    assert events[0].payload["rows_returned"] == 3


@pytest.mark.asyncio
async def test_audit_records_a_refused_read_as_zero_rows(async_session: AsyncSession) -> None:
    """A read that returned nothing is the entry worth keeping."""
    institution = Institution(name="Audit Denial School")
    async_session.add(institution)
    await async_session.flush()

    await record_event(
        async_session,
        institution_id=institution.id,
        event_type=AuditAction.SCOPED_READ,
        entity_type="insights.students",
        payload={"resource": "insights.students", "rows_returned": 0, "detail": "grade=Grade 10"},
    )
    await async_session.commit()

    events = await list_events(async_session, institution_id=institution.id)
    assert events[0].payload["rows_returned"] == 0


@pytest.mark.asyncio
async def test_audit_is_scoped_to_one_institution(async_session: AsyncSession) -> None:
    first = Institution(name="Tenant One")
    second = Institution(name="Tenant Two")
    async_session.add_all([first, second])
    await async_session.flush()

    await record_event(
        async_session,
        institution_id=first.id,
        event_type=AuditAction.LOGIN,
        entity_type="user",
    )
    await record_event(
        async_session,
        institution_id=second.id,
        event_type=AuditAction.LOGIN,
        entity_type="user",
    )
    await async_session.commit()

    assert len(await list_events(async_session, institution_id=first.id)) == 1
    total = await async_session.scalar(select(func.count()).select_from(AuditEvent))
    assert total == 2

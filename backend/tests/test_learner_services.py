"""Async service tests for materials, enrollments, and quiz attempts."""

from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from education_platform.api.deps import Principal
from education_platform.modules.academics.service import (
    assert_can_access_subtopic,
    enroll_student_in_poc_math,
    list_my_enrollments,
)
from education_platform.modules.assessments.models import QuestionAnswerKey, QuizItem
from education_platform.modules.assessments.schemas import AnswerSubmission, SubmitAttemptRequest
from education_platform.modules.assessments.service import (
    get_attempt,
    start_attempt,
    submit_attempt,
)
from education_platform.modules.auth.schemas import ProvisionStudentRequest
from education_platform.modules.auth.service import provision_student
from education_platform.modules.materials.schemas import MaterialProgressUpdate
from education_platform.modules.materials.seed import seed_approved_materials
from education_platform.modules.materials.service import (
    get_lesson,
    get_quiz,
    list_topics,
    update_material_progress,
)


def _seed(migrated_db: object) -> None:
    engine = create_engine(f"sqlite:///{migrated_db}")
    with Session(engine) as sync:
        seed_approved_materials(sync, replace=True)
    engine.dispose()


async def _student_principal(session: AsyncSession) -> Principal:
    me = await provision_student(
        session,
        ProvisionStudentRequest(
            email="svc-student@example.com",
            password="password123",
            full_name="Service Student",
            student_identifier="SVC-1",
        ),
    )
    assert me.student_profile_id is not None
    await enroll_student_in_poc_math(session, student_profile_id=me.student_profile_id)
    return Principal(
        user_id=me.id,
        institution_id=me.institution_id,
        email=me.email,
        roles=frozenset(me.roles),
        student_profile_id=me.student_profile_id,
        status=me.status,
    )


@pytest.mark.asyncio
async def test_materials_and_attempt_flow(
    async_db_session: AsyncSession, migrated_db: object
) -> None:
    _seed(migrated_db)
    principal = await _student_principal(async_db_session)

    topics = await list_topics(async_db_session, principal)
    assert {topic.id for topic in topics} >= {
        "rectangles_squares_properties",
        "square_numbers_patterns",
    }

    lesson = await get_lesson(async_db_session, principal, "rectangles_squares_properties")
    assert lesson.slides
    quiz = await get_quiz(async_db_session, principal, "square_numbers_patterns")
    assert len(quiz.questions) == 10
    lesson_for_quiz = await get_lesson(async_db_session, principal, "square_numbers_patterns")
    await update_material_progress(
        async_db_session,
        principal,
        UUID(lesson_for_quiz.id),
        MaterialProgressUpdate(status="completed"),
    )

    enrollments = await list_my_enrollments(async_db_session, principal)
    assert enrollments.subject_enrollments

    started = await start_attempt(async_db_session, principal, quiz.id)
    assert started.status == "in_progress"

    items = (
        await async_db_session.scalars(
            select(QuizItem)
            .where(QuizItem.quiz_version_id == started.quiz_version_id)
            .order_by(QuizItem.sequence)
        )
    ).all()
    answers: list[AnswerSubmission] = []
    for item in items:
        key = await async_db_session.scalar(
            select(QuestionAnswerKey).where(
                QuestionAnswerKey.question_version_id == item.question_version_id
            )
        )
        assert key is not None and key.correct_option_label is not None
        answers.append(
            AnswerSubmission(
                question_number=item.sequence,
                selected_option_label=key.correct_option_label,
            )
        )

    result = await submit_attempt(
        async_db_session,
        principal,
        started.id,
        SubmitAttemptRequest(answers=answers),
    )
    assert result.passed is True
    assert float(result.score_percent or 0) == 100.0

    fetched = await get_attempt(async_db_session, principal, UUID(str(started.id)))
    assert fetched.score_percent == result.score_percent

    with pytest.raises(HTTPException) as exc:
        await submit_attempt(
            async_db_session,
            principal,
            started.id,
            SubmitAttemptRequest(answers=answers),
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_unenrolled_student_blocked(
    async_db_session: AsyncSession, migrated_db: object
) -> None:
    _seed(migrated_db)
    me = await provision_student(
        async_db_session,
        ProvisionStudentRequest(
            email="blocked@example.com",
            password="password123",
            full_name="Blocked",
            student_identifier="BLK-1",
        ),
    )
    principal = Principal(
        user_id=me.id,
        institution_id=me.institution_id,
        email=me.email,
        roles=frozenset(me.roles),
        student_profile_id=me.student_profile_id,
        status=me.status,
    )
    topics = await list_topics(async_db_session, principal)
    assert topics == []
    with pytest.raises(HTTPException) as exc:
        await get_lesson(async_db_session, principal, "rectangles_squares_properties")
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException):
        await start_attempt(async_db_session, principal, "rectangles_squares_properties")


@pytest.mark.asyncio
async def test_missing_topic(async_db_session: AsyncSession, migrated_db: object) -> None:
    _seed(migrated_db)
    principal = await _student_principal(async_db_session)
    with pytest.raises(HTTPException) as exc:
        await get_lesson(async_db_session, principal, "missing")
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException):
        await assert_can_access_subtopic(
            async_db_session, principal, UUID("00000000-0000-0000-0000-000000000001")
        )

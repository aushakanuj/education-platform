"""Quiz attempt start/submit/score logic."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.api.deps import Principal
from education_platform.core.config import get_settings
from education_platform.modules.academics.models import Subtopic
from education_platform.modules.academics.service import assert_can_access_subtopic
from education_platform.modules.assessments.models import (
    AttemptAnswer,
    CommonMasteryQuiz,
    QuestionAnswerKey,
    QuestionVersion,
    QuizAttempt,
    QuizAttemptStatus,
    QuizItem,
    QuizVersion,
    QuizVersionStatus,
)
from education_platform.modules.assessments.schemas import (
    AttemptAnswerOut,
    AttemptResult,
    StartAttemptResponse,
    SubmitAttemptRequest,
)
from education_platform.modules.materials.service import get_subtopic_by_slug


async def _released_quiz_version(
    session: AsyncSession, subtopic_id: UUID
) -> tuple[CommonMasteryQuiz, QuizVersion]:
    quiz = await session.scalar(
        select(CommonMasteryQuiz).where(CommonMasteryQuiz.subtopic_id == subtopic_id)
    )
    if quiz is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    quiz_version = await session.scalar(
        select(QuizVersion)
        .where(
            QuizVersion.quiz_id == quiz.id,
            QuizVersion.lifecycle_status == QuizVersionStatus.RELEASED,
        )
        .order_by(QuizVersion.version_number.desc())
    )
    if quiz_version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    return quiz, quiz_version


async def start_attempt(
    session: AsyncSession, principal: Principal, topic_id: str
) -> StartAttemptResponse:
    if principal.student_profile_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Student profile required"
        )
    subtopic = await get_subtopic_by_slug(session, topic_id)
    await assert_can_access_subtopic(session, principal, subtopic.id)
    _quiz, quiz_version = await _released_quiz_version(session, subtopic.id)

    current_max = await session.scalar(
        select(func.max(QuizAttempt.attempt_number)).where(
            QuizAttempt.student_id == principal.student_profile_id,
            QuizAttempt.quiz_version_id == quiz_version.id,
        )
    )
    attempt_number = int(current_max or 0) + 1
    now = datetime.now(UTC)
    attempt = QuizAttempt(
        student_id=principal.student_profile_id,
        quiz_version_id=quiz_version.id,
        attempt_number=attempt_number,
        status=QuizAttemptStatus.IN_PROGRESS,
        started_at=now,
    )
    session.add(attempt)
    await session.commit()
    await session.refresh(attempt)
    return StartAttemptResponse(
        id=attempt.id,
        topic_id=topic_id,
        quiz_version_id=quiz_version.id,
        attempt_number=attempt.attempt_number,
        status=attempt.status.value,
        started_at=attempt.started_at,
    )


async def _owned_attempt(
    session: AsyncSession, principal: Principal, attempt_id: UUID
) -> QuizAttempt:
    attempt = await session.get(QuizAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found")
    if principal.student_profile_id is None or attempt.student_id != principal.student_profile_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found")
    return attempt


async def _topic_id_for_quiz_version(session: AsyncSession, quiz_version_id: UUID) -> str:
    quiz = await session.scalar(
        select(CommonMasteryQuiz)
        .join(QuizVersion, QuizVersion.quiz_id == CommonMasteryQuiz.id)
        .where(QuizVersion.id == quiz_version_id)
    )
    if quiz is None:
        return "unknown"
    subtopic = await session.get(Subtopic, quiz.subtopic_id)
    return subtopic.slug if subtopic else "unknown"


async def submit_attempt(
    session: AsyncSession,
    principal: Principal,
    attempt_id: UUID,
    payload: SubmitAttemptRequest,
) -> AttemptResult:
    attempt = await _owned_attempt(session, principal, attempt_id)
    if attempt.status not in {QuizAttemptStatus.IN_PROGRESS, QuizAttemptStatus.NOT_STARTED}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Attempt is not open for submission"
        )

    quiz_version = await session.get(QuizVersion, attempt.quiz_version_id)
    if quiz_version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")

    items = (
        await session.scalars(
            select(QuizItem)
            .where(QuizItem.quiz_version_id == quiz_version.id)
            .order_by(QuizItem.sequence)
        )
    ).all()
    item_by_number = {item.sequence: item for item in items}
    answers_by_number = {answer.question_number: answer for answer in payload.answers}

    total_marks = Decimal("0")
    earned = Decimal("0")
    answer_rows: list[AttemptAnswer] = []

    for number, item in item_by_number.items():
        version = await session.get(QuestionVersion, item.question_version_id)
        if version is None:
            continue
        key = await session.scalar(
            select(QuestionAnswerKey).where(QuestionAnswerKey.question_version_id == version.id)
        )
        selected = answers_by_number.get(number)
        selected_label = selected.selected_option_label.upper() if selected else None
        is_correct = bool(
            key is not None
            and selected_label is not None
            and key.correct_option_label is not None
            and selected_label == key.correct_option_label.upper()
        )
        marks = version.marks if is_correct else Decimal("0")
        total_marks += version.marks
        earned += marks
        answer_rows.append(
            AttemptAnswer(
                attempt_id=attempt.id,
                question_version_id=version.id,
                selected_option_label=selected_label,
                is_correct=is_correct,
                marks_awarded=marks,
            )
        )

    existing = (
        await session.scalars(select(AttemptAnswer).where(AttemptAnswer.attempt_id == attempt.id))
    ).all()
    for row in existing:
        await session.delete(row)

    for row in answer_rows:
        session.add(row)

    now = datetime.now(UTC)
    percent = (
        (earned / total_marks * Decimal("100")).quantize(Decimal("0.01"))
        if total_marks > 0
        else Decimal("0")
    )
    pass_threshold = Decimal(str(get_settings().mastery_pass_percent))
    attempt.status = QuizAttemptStatus.SCORED
    attempt.submitted_at = now
    attempt.scored_at = now
    attempt.score_raw = earned
    attempt.score_percent = percent
    attempt.passed = percent >= pass_threshold
    await session.commit()

    topic_id = await _topic_id_for_quiz_version(session, quiz_version.id)
    return await get_attempt(session, principal, attempt.id, topic_id=topic_id)


async def get_attempt(
    session: AsyncSession,
    principal: Principal,
    attempt_id: UUID,
    *,
    topic_id: str | None = None,
) -> AttemptResult:
    attempt = await _owned_attempt(session, principal, attempt_id)
    resolved_topic = topic_id or await _topic_id_for_quiz_version(session, attempt.quiz_version_id)
    items = (
        await session.scalars(
            select(QuizItem)
            .where(QuizItem.quiz_version_id == attempt.quiz_version_id)
            .order_by(QuizItem.sequence)
        )
    ).all()
    number_by_qv = {item.question_version_id: item.sequence for item in items}
    answers = (
        await session.scalars(select(AttemptAnswer).where(AttemptAnswer.attempt_id == attempt.id))
    ).all()

    return AttemptResult(
        id=attempt.id,
        topic_id=resolved_topic,
        attempt_number=attempt.attempt_number,
        status=attempt.status.value,
        started_at=attempt.started_at,
        submitted_at=attempt.submitted_at,
        scored_at=attempt.scored_at,
        score_raw=attempt.score_raw,
        score_percent=attempt.score_percent,
        passed=attempt.passed,
        answers=[
            AttemptAnswerOut(
                question_number=number_by_qv.get(answer.question_version_id, 0),
                selected_option_label=answer.selected_option_label,
                is_correct=answer.is_correct,
                marks_awarded=answer.marks_awarded,
            )
            for answer in answers
            if number_by_qv.get(answer.question_version_id)
        ],
    )

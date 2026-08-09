"""Quiz attempt start/submit/score logic."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.api.deps import Principal
from education_platform.modules.academics.models import Subtopic
from education_platform.modules.academics.service import (
    AccessContext,
    resolve_subtopic_access,
    resolve_topic_access,
)
from education_platform.modules.assessments.models import (
    AttemptAnswer,
    CommonMasteryQuiz,
    QuestionAnswerKey,
    QuestionOption,
    QuestionVersion,
    QuizAttempt,
    QuizAttemptStatus,
    QuizItem,
    QuizResultReleaseMode,
    QuizScope,
    QuizVersion,
    QuizVersionStatus,
)
from education_platform.modules.assessments.schemas import (
    AttemptAnswerOut,
    AttemptResult,
    StartAttemptResponse,
    SubmitAttemptRequest,
)
from education_platform.modules.materials.models import (
    MaterialProgressStatus,
    SourceMaterial,
    SourceMaterialVersion,
    SourceMaterialVersionStatus,
    StudentMaterialProgress,
)
from education_platform.modules.materials.schemas import AttemptHistoryItem
from education_platform.modules.materials.service import (
    get_subtopic_by_slug,
    open_release_for_quiz_version,
    questions_for_quiz_version,
)


async def _released_quiz_version_by_quiz_id(
    session: AsyncSession, quiz_id: UUID
) -> tuple[CommonMasteryQuiz, QuizVersion]:
    row = (
        await session.execute(
            select(CommonMasteryQuiz, QuizVersion)
            .join(QuizVersion, QuizVersion.quiz_id == CommonMasteryQuiz.id)
            .where(
                CommonMasteryQuiz.id == quiz_id,
                QuizVersion.lifecycle_status == QuizVersionStatus.RELEASED,
            )
            .order_by(QuizVersion.version_number.desc())
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    return row[0], row[1]


async def _access_for_quiz(
    session: AsyncSession, principal: Principal, quiz: CommonMasteryQuiz
) -> AccessContext:
    if quiz.quiz_scope == QuizScope.SUBTOPIC_MASTERY and quiz.subtopic_id is not None:
        return await resolve_subtopic_access(session, principal, quiz.subtopic_id)
    if quiz.quiz_scope == QuizScope.TOPIC_MASTERY and quiz.topic_id is not None:
        return await resolve_topic_access(session, principal, quiz.topic_id)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")


async def _ensure_lesson_completed(session: AsyncSession, context: AccessContext) -> None:
    if context.subtopic is None or context.subject_enrollment is None:
        return
    version = await session.scalar(
        select(SourceMaterialVersion)
        .join(SourceMaterial, SourceMaterial.id == SourceMaterialVersion.source_material_id)
        .where(
            SourceMaterial.subtopic_id == context.subtopic.id,
            SourceMaterialVersion.lifecycle_status == SourceMaterialVersionStatus.PUBLISHED,
        )
        .order_by(SourceMaterialVersion.version_number.desc())
    )
    if version is None:
        return
    progress = await session.scalar(
        select(StudentMaterialProgress).where(
            StudentMaterialProgress.student_subject_enrollment_id == context.subject_enrollment.id,
            StudentMaterialProgress.source_material_version_id == version.id,
            StudentMaterialProgress.status == MaterialProgressStatus.COMPLETED,
        )
    )
    if progress is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Complete the lesson first"
        )


async def _ensure_subtopic_quizzes_passed(
    session: AsyncSession, principal: Principal, context: AccessContext
) -> None:
    if principal.student_profile_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Student profile required"
        )
    subtopic_ids = (
        await session.scalars(select(Subtopic.id).where(Subtopic.topic_id == context.topic.id))
    ).all()
    for subtopic_id in subtopic_ids:
        row = (
            await session.execute(
                select(CommonMasteryQuiz, QuizVersion)
                .join(QuizVersion, QuizVersion.quiz_id == CommonMasteryQuiz.id)
                .where(
                    CommonMasteryQuiz.quiz_scope == QuizScope.SUBTOPIC_MASTERY,
                    CommonMasteryQuiz.subtopic_id == subtopic_id,
                    QuizVersion.lifecycle_status == QuizVersionStatus.RELEASED,
                )
                .order_by(QuizVersion.version_number.desc())
            )
        ).first()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Pass all subtopic quizzes first",
            )
        _quiz, version = row
        passed = await session.scalar(
            select(QuizAttempt.id).where(
                QuizAttempt.student_id == principal.student_profile_id,
                QuizAttempt.quiz_version_id == version.id,
                QuizAttempt.passed.is_(True),
            )
        )
        if passed is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Pass all subtopic quizzes first",
            )


async def start_attempt(
    session: AsyncSession, principal: Principal, quiz_id: UUID | str
) -> StartAttemptResponse:
    if isinstance(quiz_id, str):
        try:
            quiz_uuid = UUID(quiz_id)
        except ValueError:
            subtopic = await get_subtopic_by_slug(session, quiz_id)
            quiz = await session.scalar(
                select(CommonMasteryQuiz).where(
                    CommonMasteryQuiz.subtopic_id == subtopic.id,
                    CommonMasteryQuiz.quiz_scope == QuizScope.SUBTOPIC_MASTERY,
                )
            )
            if quiz is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found"
                ) from None
            quiz_uuid = quiz.id
    else:
        quiz_uuid = quiz_id
    if principal.student_profile_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Student profile required"
        )
    quiz, quiz_version = await _released_quiz_version_by_quiz_id(session, quiz_uuid)
    context = await _access_for_quiz(session, principal, quiz)
    if context.subject_enrollment is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Student enrollment required"
        )
    if quiz.quiz_scope == QuizScope.SUBTOPIC_MASTERY:
        await _ensure_lesson_completed(session, context)
    else:
        await _ensure_subtopic_quizzes_passed(session, principal, context)
    release = await open_release_for_quiz_version(session, quiz_version.id)
    if release is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Quiz is not open")

    in_progress = await session.scalar(
        select(QuizAttempt).where(
            QuizAttempt.student_id == principal.student_profile_id,
            QuizAttempt.quiz_version_id == quiz_version.id,
            QuizAttempt.status == QuizAttemptStatus.IN_PROGRESS,
        )
    )
    if in_progress is not None:
        return await _start_response(session, quiz, quiz_version, in_progress)

    current_max = await session.scalar(
        select(func.max(QuizAttempt.attempt_number)).where(
            QuizAttempt.student_id == principal.student_profile_id,
            QuizAttempt.quiz_version_id == quiz_version.id,
        )
    )
    attempt_number = int(current_max or 0) + 1
    if quiz_version.max_attempts is not None and attempt_number > quiz_version.max_attempts:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Maximum attempts reached")
    now = datetime.now(UTC)
    deadline_at = (
        now + timedelta(seconds=quiz_version.duration_seconds)
        if quiz_version.duration_seconds is not None
        else None
    )
    attempt = QuizAttempt(
        student_id=principal.student_profile_id,
        student_subject_enrollment_id=context.subject_enrollment.id,
        quiz_version_id=quiz_version.id,
        quiz_release_id=release.id,
        attempt_number=attempt_number,
        status=QuizAttemptStatus.IN_PROGRESS,
        started_at=now,
        deadline_at=deadline_at,
        pass_threshold_percent=quiz_version.pass_threshold_percent,
    )
    session.add(attempt)
    await session.commit()
    await session.refresh(attempt)
    return await _start_response(session, quiz, quiz_version, attempt)


async def _start_response(
    session: AsyncSession,
    quiz: CommonMasteryQuiz,
    quiz_version: QuizVersion,
    attempt: QuizAttempt,
) -> StartAttemptResponse:
    target_id = quiz.subtopic_id if quiz.subtopic_id is not None else quiz.topic_id
    if target_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    return StartAttemptResponse(
        id=attempt.id,
        quiz_id=quiz.id,
        quiz_version_id=quiz_version.id,
        attempt_number=attempt.attempt_number,
        status=attempt.status.value,
        started_at=attempt.started_at,
        deadline_at=attempt.deadline_at,
        pass_threshold_percent=quiz_version.pass_threshold_percent,
        result_release_mode=quiz_version.result_release_mode.value,
        questions=await questions_for_quiz_version(session, quiz_version.id),
        title=quiz.title,
        scope=quiz.quiz_scope.value,
        target_id=target_id,
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


async def _quiz_for_quiz_version(session: AsyncSession, quiz_version_id: UUID) -> CommonMasteryQuiz:
    quiz = await session.scalar(
        select(CommonMasteryQuiz)
        .join(QuizVersion, QuizVersion.quiz_id == CommonMasteryQuiz.id)
        .where(QuizVersion.id == quiz_version_id)
    )
    if quiz is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    return quiz


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
    if attempt.deadline_at is not None:
        deadline = attempt.deadline_at
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=UTC)
        if deadline < datetime.now(UTC):
            attempt.status = QuizAttemptStatus.EXPIRED
            await session.commit()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Attempt expired")

    items = (
        await session.scalars(
            select(QuizItem)
            .where(QuizItem.quiz_version_id == quiz_version.id)
            .order_by(QuizItem.sequence)
        )
    ).all()
    item_by_number = {item.sequence: item for item in items}
    numbers = [answer.question_number for answer in payload.answers]
    if len(numbers) != len(set(numbers)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Duplicate answers"
        )
    if set(numbers) != set(item_by_number):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Answers must match the quiz question set",
        )
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
        label_exists = await session.scalar(
            select(QuestionOption.id).where(
                QuestionOption.question_version_id == version.id,
                QuestionOption.label == selected_label,
            )
        )
        if label_exists is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid option for question {number}",
            )
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
    pass_threshold = quiz_version.pass_threshold_percent
    attempt.status = (
        QuizAttemptStatus.HELD
        if quiz_version.result_release_mode == QuizResultReleaseMode.ADMIN_RELEASE
        else QuizAttemptStatus.SCORED
    )
    attempt.submitted_at = now
    attempt.scored_at = now
    attempt.score_raw = earned
    attempt.score_percent = percent
    attempt.pass_threshold_percent = pass_threshold
    attempt.passed = percent >= pass_threshold
    await session.commit()

    return await get_attempt(session, principal, attempt.id)


async def get_attempt(
    session: AsyncSession,
    principal: Principal,
    attempt_id: UUID,
) -> AttemptResult:
    attempt = await _owned_attempt(session, principal, attempt_id)
    quiz = await _quiz_for_quiz_version(session, attempt.quiz_version_id)
    quiz_version = await session.get(QuizVersion, attempt.quiz_version_id)
    review_available = not (
        quiz_version is not None
        and quiz_version.result_release_mode == QuizResultReleaseMode.ADMIN_RELEASE
        and attempt.status == QuizAttemptStatus.HELD
    )
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

    target_id = quiz.subtopic_id if quiz.subtopic_id is not None else quiz.topic_id
    return AttemptResult(
        id=attempt.id,
        quiz_id=quiz.id,
        target_id=target_id,
        scope=quiz.quiz_scope.value,
        attempt_number=attempt.attempt_number,
        status=attempt.status.value,
        started_at=attempt.started_at,
        deadline_at=attempt.deadline_at,
        submitted_at=attempt.submitted_at,
        scored_at=attempt.scored_at,
        score_raw=attempt.score_raw if review_available else None,
        score_percent=attempt.score_percent if review_available else None,
        pass_threshold_percent=attempt.pass_threshold_percent,
        passed=attempt.passed if review_available else None,
        review_available=review_available,
        answers=[
            AttemptAnswerOut(
                question_number=number_by_qv.get(answer.question_version_id, 0),
                selected_option_label=answer.selected_option_label,
                is_correct=answer.is_correct if review_available else None,
                marks_awarded=answer.marks_awarded if review_available else None,
            )
            for answer in answers
            if number_by_qv.get(answer.question_version_id)
        ]
        if review_available
        else [],
    )


async def list_attempts_for_quiz(
    session: AsyncSession, principal: Principal, quiz_id: UUID
) -> list[AttemptHistoryItem]:
    if principal.student_profile_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Student profile required"
        )
    quiz, _version = await _released_quiz_version_by_quiz_id(session, quiz_id)
    await _access_for_quiz(session, principal, quiz)
    version_ids = (
        await session.scalars(select(QuizVersion.id).where(QuizVersion.quiz_id == quiz.id))
    ).all()
    attempts = (
        await session.scalars(
            select(QuizAttempt)
            .where(
                QuizAttempt.student_id == principal.student_profile_id,
                QuizAttempt.quiz_version_id.in_(version_ids),
            )
            .order_by(QuizAttempt.attempt_number.desc())
        )
    ).all()
    return [
        AttemptHistoryItem(
            id=attempt.id,
            attempt_number=attempt.attempt_number,
            status=attempt.status.value,
            score_percent=attempt.score_percent,
            passed=attempt.passed,
            submitted_at=attempt.submitted_at,
            started_at=attempt.started_at,
        )
        for attempt in attempts
    ]

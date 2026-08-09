"""Development-only demo bootstrap / reset helpers for mock UI parity."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.api.deps import Principal
from education_platform.modules.academics.models import (
    EnrollmentStatus,
    GradeSubjectOffering,
    StudentSubjectEnrollment,
    Subject,
    Subtopic,
    Topic,
)
from education_platform.modules.academics.schemas import DemoBootstrapOut, DemoResetOut
from education_platform.modules.academics.service import enroll_student_in_poc_math
from education_platform.modules.assessments.models import (
    AttemptAnswer,
    CommonMasteryQuiz,
    QuizAttempt,
    QuizAttemptStatus,
    QuizScope,
    QuizVersion,
    QuizVersionStatus,
)
from education_platform.modules.materials.models import (
    MaterialProgressStatus,
    SourceMaterial,
    SourceMaterialVersion,
    SourceMaterialVersionStatus,
    StudentMaterialProgress,
)
from education_platform.modules.materials.service import open_release_for_quiz_version


async def _require_student(principal: Principal) -> UUID:
    if principal.student_profile_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Student profile required"
        )
    return principal.student_profile_id


async def _active_subject_enrollment(
    session: AsyncSession, student_id: UUID
) -> StudentSubjectEnrollment:
    enrollment = await session.scalar(
        select(StudentSubjectEnrollment)
        .where(
            StudentSubjectEnrollment.student_id == student_id,
            StudentSubjectEnrollment.status == EnrollmentStatus.ACTIVE,
        )
        .limit(1)
    )
    if enrollment is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active subject enrollment required",
        )
    return enrollment


async def bootstrap_demo(session: AsyncSession, principal: Principal) -> DemoBootstrapOut:
    student_id = await _require_student(principal)
    await enroll_student_in_poc_math(session, student_profile_id=student_id)
    enrollment = await _active_subject_enrollment(session, student_id)

    subject = await session.scalar(
        select(Subject)
        .join(GradeSubjectOffering, GradeSubjectOffering.subject_id == Subject.id)
        .where(GradeSubjectOffering.id == enrollment.grade_subject_offering_id)
    )
    if subject is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")

    topic = await session.scalar(
        select(Topic)
        .where(Topic.grade_subject_offering_id == enrollment.grade_subject_offering_id)
        .order_by(Topic.sequence, Topic.slug)
        .limit(1)
    )
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No topics seeded")

    subtopics = (
        await session.scalars(
            select(Subtopic)
            .where(Subtopic.topic_id == topic.id)
            .order_by(Subtopic.sequence, Subtopic.slug)
        )
    ).all()
    if not subtopics:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No subtopics seeded")

    now = datetime.now(UTC)
    for subtopic in subtopics:
        await _complete_lesson(session, enrollment.id, subtopic.id, now)
        await _pass_subtopic_quiz(session, student_id, enrollment.id, subtopic.id, now)

    await session.commit()
    return DemoBootstrapOut(
        subject_id=subject.id,
        topic_id=topic.id,
        topic_title=topic.name,
        message=(
            "All subtopics are marked complete with quiz history, "
            "so the overall topic quiz is unlocked."
        ),
    )


async def _complete_lesson(
    session: AsyncSession,
    enrollment_id: UUID,
    subtopic_id: UUID,
    now: datetime,
) -> None:
    version = await session.scalar(
        select(SourceMaterialVersion)
        .join(SourceMaterial, SourceMaterial.id == SourceMaterialVersion.source_material_id)
        .where(
            SourceMaterial.subtopic_id == subtopic_id,
            SourceMaterialVersion.lifecycle_status == SourceMaterialVersionStatus.PUBLISHED,
        )
        .order_by(SourceMaterialVersion.version_number.desc())
    )
    if version is None:
        return
    progress = await session.scalar(
        select(StudentMaterialProgress).where(
            StudentMaterialProgress.student_subject_enrollment_id == enrollment_id,
            StudentMaterialProgress.source_material_version_id == version.id,
        )
    )
    if progress is None:
        session.add(
            StudentMaterialProgress(
                student_subject_enrollment_id=enrollment_id,
                source_material_version_id=version.id,
                status=MaterialProgressStatus.COMPLETED,
                opened_at=now,
                last_opened_at=now,
                last_unit_ordinal=1,
                completed_at=now,
            )
        )
    else:
        progress.status = MaterialProgressStatus.COMPLETED
        progress.last_opened_at = now
        progress.last_unit_ordinal = max(progress.last_unit_ordinal or 1, 1)
        progress.completed_at = progress.completed_at or now


async def _pass_subtopic_quiz(
    session: AsyncSession,
    student_id: UUID,
    enrollment_id: UUID,
    subtopic_id: UUID,
    now: datetime,
) -> None:
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
        return
    _quiz, quiz_version = row
    release = await open_release_for_quiz_version(session, quiz_version.id)

    in_progress = (
        await session.scalars(
            select(QuizAttempt).where(
                QuizAttempt.student_id == student_id,
                QuizAttempt.quiz_version_id == quiz_version.id,
                QuizAttempt.status == QuizAttemptStatus.IN_PROGRESS,
            )
        )
    ).all()
    for attempt in in_progress:
        await session.execute(delete(AttemptAnswer).where(AttemptAnswer.attempt_id == attempt.id))
        await session.delete(attempt)
    await session.flush()

    already_passed = await session.scalar(
        select(QuizAttempt.id).where(
            QuizAttempt.student_id == student_id,
            QuizAttempt.quiz_version_id == quiz_version.id,
            QuizAttempt.passed.is_(True),
        )
    )
    if already_passed is not None:
        return

    current_max = await session.scalar(
        select(func.max(QuizAttempt.attempt_number)).where(
            QuizAttempt.student_id == student_id,
            QuizAttempt.quiz_version_id == quiz_version.id,
        )
    )
    session.add(
        QuizAttempt(
            student_id=student_id,
            student_subject_enrollment_id=enrollment_id,
            quiz_version_id=quiz_version.id,
            quiz_release_id=release.id if release else None,
            attempt_number=int(current_max or 0) + 1,
            status=QuizAttemptStatus.RELEASED,
            started_at=now,
            submitted_at=now,
            scored_at=now,
            score_raw=Decimal("1.00"),
            score_percent=Decimal("100.00"),
            pass_threshold_percent=quiz_version.pass_threshold_percent,
            passed=True,
        )
    )


async def reset_demo(session: AsyncSession, principal: Principal) -> DemoResetOut:
    student_id = await _require_student(principal)
    enrollment_ids = list(
        await session.scalars(
            select(StudentSubjectEnrollment.id).where(
                StudentSubjectEnrollment.student_id == student_id
            )
        )
    )

    attempt_ids = list(
        await session.scalars(select(QuizAttempt.id).where(QuizAttempt.student_id == student_id))
    )
    if attempt_ids:
        await session.execute(
            delete(AttemptAnswer).where(AttemptAnswer.attempt_id.in_(attempt_ids))
        )
        await session.execute(delete(QuizAttempt).where(QuizAttempt.id.in_(attempt_ids)))

    if enrollment_ids:
        await session.execute(
            delete(StudentMaterialProgress).where(
                StudentMaterialProgress.student_subject_enrollment_id.in_(enrollment_ids)
            )
        )

    await session.commit()
    return DemoResetOut(status="ok", message="Demo progress cleared")

"""Materials catalog and content reads from SQLite."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.modules.academics.models import (
    AcademicPeriod,
    EnrollmentStatus,
    Grade,
    GradeSubjectOffering,
    LearningOutcome,
    PeriodGrade,
    StudentSubjectEnrollment,
    Subject,
    Subtopic,
    Topic,
)
from education_platform.modules.academics.service import (
    CurriculumNode,
    load_subtopic_node,
    subject_enrollment_for,
)
from education_platform.modules.assessments.models import (
    CommonMasteryQuiz,
    QuestionOption,
    QuestionVersion,
    QuizAttempt,
    QuizAttemptStatus,
    QuizItem,
    QuizRelease,
    QuizReleaseStatus,
    QuizScope,
    QuizVersion,
    QuizVersionStatus,
)
from education_platform.modules.authorization.scope import Scope
from education_platform.modules.materials.markdown_parser import parse_slides
from education_platform.modules.materials.models import (
    MaterialProgressStatus,
    SourceMaterial,
    SourceMaterialVersion,
    SourceMaterialVersionStatus,
    StudentMaterialProgress,
)
from education_platform.modules.materials.schemas import (
    AttemptHistoryItem,
    LearningDirectoryOut,
    LessonMaterial,
    LessonSlide,
    MaterialProgressOut,
    MaterialProgressUpdate,
    QuizMaterial,
    QuizOption,
    QuizQuestion,
    QuizSummaryOut,
    SubjectNodeOut,
    SubtopicNodeOut,
    TopicNodeOut,
    TopicSummary,
)


def _progress_out(progress: StudentMaterialProgress | None) -> MaterialProgressOut | None:
    if progress is None:
        return None
    return MaterialProgressOut(
        status=progress.status.value,
        opened_at=progress.opened_at,
        last_opened_at=progress.last_opened_at,
        completed_at=progress.completed_at,
        last_unit_ordinal=progress.last_unit_ordinal,
        source_material_version_id=progress.source_material_version_id,
    )


async def _published_material_version(
    session: AsyncSession, subtopic_id: UUID
) -> SourceMaterialVersion | None:
    return cast(
        SourceMaterialVersion | None,
        await session.scalar(
            select(SourceMaterialVersion)
            .join(SourceMaterial, SourceMaterial.id == SourceMaterialVersion.source_material_id)
            .where(
                SourceMaterial.subtopic_id == subtopic_id,
                SourceMaterialVersion.lifecycle_status == SourceMaterialVersionStatus.PUBLISHED,
            )
            .order_by(SourceMaterialVersion.version_number.desc())
        ),
    )


async def _progress_for(
    session: AsyncSession,
    subject_enrollment_id: UUID | None,
    version_id: UUID | None,
) -> StudentMaterialProgress | None:
    if subject_enrollment_id is None or version_id is None:
        return None
    return cast(
        StudentMaterialProgress | None,
        await session.scalar(
            select(StudentMaterialProgress).where(
                StudentMaterialProgress.student_subject_enrollment_id == subject_enrollment_id,
                StudentMaterialProgress.source_material_version_id == version_id,
            )
        ),
    )


async def list_topics(session: AsyncSession, scope: Scope) -> list[TopicSummary]:
    directory = await build_learning_directory(session, scope)
    topics: list[TopicSummary] = []
    for subject in directory.subjects:
        for topic in subject.topics:
            for subtopic in topic.subtopics:
                has_quiz = bool(subtopic.quiz and subtopic.quiz.available)
                if not subtopic.has_lesson and not has_quiz:
                    continue
                topics.append(
                    TopicSummary(
                        id=subtopic.slug,
                        title=subtopic.title,
                        has_lesson=subtopic.has_lesson,
                        has_quiz=has_quiz,
                    )
                )
    return topics


async def build_learning_directory(session: AsyncSession, scope: Scope) -> LearningDirectoryOut:
    offering_query = (
        select(GradeSubjectOffering, Subject, AcademicPeriod, Grade)
        .join(Subject, Subject.id == GradeSubjectOffering.subject_id)
        .join(PeriodGrade, PeriodGrade.id == GradeSubjectOffering.period_grade_id)
        .join(Grade, Grade.id == PeriodGrade.grade_id)
        .join(AcademicPeriod, AcademicPeriod.id == PeriodGrade.academic_period_id)
        .where(Subject.institution_id == scope.institution_id)
        .order_by(Grade.sort_order, Subject.code)
    )
    if not scope.unrestricted:
        if not scope.offering_ids:
            return LearningDirectoryOut(subjects=[])
        offering_query = offering_query.where(GradeSubjectOffering.id.in_(scope.offering_ids))

    subject_rows = [
        (offering, subject, period, grade)
        for offering, subject, period, grade in (await session.execute(offering_query)).all()
    ]

    enrollment_by_offering: dict[UUID, StudentSubjectEnrollment] = {}
    if not scope.unrestricted and scope.self_student_id is not None and subject_rows:
        enrollments = (
            await session.scalars(
                select(StudentSubjectEnrollment).where(
                    StudentSubjectEnrollment.student_id == scope.self_student_id,
                    StudentSubjectEnrollment.status == EnrollmentStatus.ACTIVE,
                    StudentSubjectEnrollment.grade_subject_offering_id.in_(
                        [offering.id for offering, *_ in subject_rows]
                    ),
                )
            )
        ).all()
        enrollment_by_offering = {
            enrollment.grade_subject_offering_id: enrollment for enrollment in enrollments
        }

    subjects: list[SubjectNodeOut] = []
    for offering, subject, period, grade in subject_rows:
        subject_enrollment = enrollment_by_offering.get(offering.id)
        topic_nodes: list[TopicNodeOut] = []
        db_topics = (
            await session.scalars(
                select(Topic)
                .where(Topic.grade_subject_offering_id == offering.id)
                .order_by(Topic.sequence, Topic.slug)
            )
        ).all()
        for topic in db_topics:
            subtopic_nodes = await _subtopic_nodes(session, scope, topic, subject_enrollment)
            quiz_nodes = [node for node in subtopic_nodes if node.quiz and node.quiz.available]
            overall_unlocked = bool(quiz_nodes) and all(
                node.quiz is not None and node.quiz.passed for node in quiz_nodes
            )
            overall = await _quiz_summary(
                session,
                scope,
                quiz_scope=QuizScope.TOPIC_MASTERY,
                target_id=topic.id,
                unlocked=overall_unlocked,
                locked_reason="Pass all subtopic quizzes first",
            )
            units = [node.progress_percent for node in subtopic_nodes]
            if overall.available:
                units.append(100 if overall.passed else 0)
            progress_percent = round(sum(units) / len(units)) if units else 0
            topic_complete = overall_unlocked and (not overall.available or overall.passed)
            objectives = await _topic_objectives(session, topic.id)
            topic_nodes.append(
                TopicNodeOut(
                    id=topic.id,
                    title=topic.name,
                    slug=topic.slug,
                    sequence=topic.sequence,
                    progress_percent=progress_percent,
                    complete=topic_complete,
                    objectives=objectives,
                    subtopics=subtopic_nodes,
                    overall_quiz=overall if overall.available else None,
                )
            )
        subject_progress = (
            round(sum(topic.progress_percent for topic in topic_nodes) / len(topic_nodes))
            if topic_nodes
            else 0
        )
        subjects.append(
            SubjectNodeOut(
                id=subject.id,
                code=subject.code,
                name=subject.name,
                grade_name=grade.name,
                academic_period_name=period.name,
                progress_percent=subject_progress,
                topics=topic_nodes,
            )
        )
    return LearningDirectoryOut(subjects=subjects)


async def _topic_objectives(session: AsyncSession, topic_id: UUID) -> list[str]:
    rows = (
        await session.execute(
            select(LearningOutcome.statement)
            .join(Subtopic, Subtopic.id == LearningOutcome.subtopic_id)
            .where(Subtopic.topic_id == topic_id)
            .order_by(Subtopic.sequence, LearningOutcome.sequence, LearningOutcome.code)
        )
    ).all()
    seen: set[str] = set()
    objectives: list[str] = []
    for (statement,) in rows:
        text = statement.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        objectives.append(text)
    return objectives


def _lesson_progress_percent(
    *,
    lesson_completed: bool,
    quiz_passed: bool,
    progress: StudentMaterialProgress | None,
    version: SourceMaterialVersion | None,
) -> int:
    if quiz_passed:
        return 100
    if lesson_completed:
        return 50
    if progress is None or version is None:
        return 0
    slides = parse_slides(version.content_markdown or "")
    total = len(slides)
    if total <= 0:
        return 5
    current = max(1, min(progress.last_unit_ordinal or 1, total))
    # Lesson share is 50% of subtopic; keep below 50 until fully completed.
    return max(1, min(49, round(50 * current / total)))


async def _subtopic_nodes(
    session: AsyncSession,
    scope: Scope,
    topic: Topic,
    subject_enrollment: StudentSubjectEnrollment | None,
) -> list[SubtopicNodeOut]:
    subtopics = (
        await session.scalars(
            select(Subtopic)
            .where(Subtopic.topic_id == topic.id)
            .order_by(Subtopic.sequence, Subtopic.slug)
        )
    ).all()
    nodes: list[SubtopicNodeOut] = []
    for subtopic in subtopics:
        version = await _published_material_version(session, subtopic.id)
        progress = await _progress_for(
            session,
            subject_enrollment.id if subject_enrollment else None,
            version.id if version else None,
        )
        lesson_completed = (
            progress is not None and progress.status == MaterialProgressStatus.COMPLETED
        )
        quiz = await _quiz_summary(
            session,
            scope,
            quiz_scope=QuizScope.SUBTOPIC_MASTERY,
            target_id=subtopic.id,
            unlocked=lesson_completed,
            locked_reason="Complete the lesson first",
        )
        progress_percent = _lesson_progress_percent(
            lesson_completed=lesson_completed,
            quiz_passed=bool(quiz.passed),
            progress=progress,
            version=version,
        )
        nodes.append(
            SubtopicNodeOut(
                id=subtopic.id,
                title=subtopic.name,
                slug=subtopic.slug,
                sequence=subtopic.sequence,
                progress_percent=progress_percent,
                has_lesson=version is not None,
                lesson_completed=lesson_completed,
                progress=_progress_out(progress),
                source_material_version_id=version.id if version else None,
                quiz=quiz if quiz.available else None,
            )
        )
    return nodes


async def _released_quiz(
    session: AsyncSession,
    *,
    quiz_scope: QuizScope,
    target_id: UUID,
) -> tuple[CommonMasteryQuiz, QuizVersion] | None:
    target_filter = (
        CommonMasteryQuiz.subtopic_id == target_id
        if quiz_scope == QuizScope.SUBTOPIC_MASTERY
        else CommonMasteryQuiz.topic_id == target_id
    )
    row = (
        await session.execute(
            select(CommonMasteryQuiz, QuizVersion)
            .join(QuizVersion, QuizVersion.quiz_id == CommonMasteryQuiz.id)
            .where(
                CommonMasteryQuiz.quiz_scope == quiz_scope,
                target_filter,
                QuizVersion.lifecycle_status == QuizVersionStatus.RELEASED,
            )
            .order_by(QuizVersion.version_number.desc())
        )
    ).first()
    return (row[0], row[1]) if row is not None else None


async def _quiz_summary(
    session: AsyncSession,
    scope: Scope,
    *,
    quiz_scope: QuizScope,
    target_id: UUID,
    unlocked: bool,
    locked_reason: str,
) -> QuizSummaryOut:
    released = await _released_quiz(session, quiz_scope=quiz_scope, target_id=target_id)
    if released is None:
        return QuizSummaryOut(id=None, scope=quiz_scope.value)
    quiz, version = released
    attempts: list[QuizAttempt] = []
    if scope.self_student_id is not None:
        version_ids = (
            await session.scalars(select(QuizVersion.id).where(QuizVersion.quiz_id == quiz.id))
        ).all()
        attempts = list(
            await session.scalars(
                select(QuizAttempt)
                .where(
                    QuizAttempt.student_id == scope.self_student_id,
                    QuizAttempt.quiz_version_id.in_(version_ids),
                    QuizAttempt.status != QuizAttemptStatus.ABANDONED,
                )
                .order_by(QuizAttempt.attempt_number.desc())
            )
        )
    best = max(
        (attempt.score_percent for attempt in attempts if attempt.score_percent is not None),
        default=None,
    )
    passed = any(attempt.passed is True for attempt in attempts)
    in_progress = next(
        (attempt for attempt in attempts if attempt.status == QuizAttemptStatus.IN_PROGRESS),
        None,
    )
    recent = [
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
    return QuizSummaryOut(
        id=quiz.id,
        title=quiz.title,
        scope=quiz_scope.value,
        available=True,
        unlocked=unlocked,
        locked_reason=None if unlocked else locked_reason,
        pass_threshold_percent=version.pass_threshold_percent,
        attempt_count=len(attempts),
        best_score_percent=best,
        passed=passed,
        in_progress_attempt_id=in_progress.id if in_progress else None,
        recent_attempts=recent,
    )


async def get_subtopic_by_slug(session: AsyncSession, topic_id: str, *, scope: Scope) -> Subtopic:
    stmt = (
        select(Subtopic)
        .join(Topic, Topic.id == Subtopic.topic_id)
        .join(
            GradeSubjectOffering,
            GradeSubjectOffering.id == Topic.grade_subject_offering_id,
        )
        .join(PeriodGrade, PeriodGrade.id == GradeSubjectOffering.period_grade_id)
        .join(AcademicPeriod, AcademicPeriod.id == PeriodGrade.academic_period_id)
        .where(
            Subtopic.slug == topic_id,
            AcademicPeriod.institution_id == scope.institution_id,
        )
        .order_by(Subtopic.sequence)
    )
    if not scope.unrestricted:
        if not scope.offering_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Topic '{topic_id}' not found",
            )
        stmt = stmt.where(GradeSubjectOffering.id.in_(scope.offering_ids))
    subtopic = await session.scalar(stmt)
    if subtopic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Topic '{topic_id}' not found",
        )
    return subtopic


async def _covered_subtopic_node(
    session: AsyncSession, scope: Scope, subtopic_id: UUID
) -> CurriculumNode:
    node = await load_subtopic_node(session, subtopic_id)
    if node is None or node.subtopic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    if not scope.covers_offering(node.offering.id, institution_id=node.institution.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    return node


async def get_lesson(session: AsyncSession, scope: Scope, topic_id: str) -> LessonMaterial:
    subtopic = await get_subtopic_by_slug(session, topic_id, scope=scope)
    return await get_subtopic_lesson(session, scope, subtopic.id)


async def get_subtopic_lesson(
    session: AsyncSession, scope: Scope, subtopic_id: UUID
) -> LessonMaterial:
    node = await _covered_subtopic_node(session, scope, subtopic_id)
    version = await _published_material_version(session, subtopic_id)
    if version is None or not version.content_markdown:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lesson not found",
        )
    enrollment = None
    if scope.self_student_id is not None:
        enrollment = await subject_enrollment_for(session, scope.self_student_id, node.offering.id)
    progress = await _progress_for(
        session,
        enrollment.id if enrollment else None,
        version.id,
    )
    quiz = await _released_quiz(
        session, quiz_scope=QuizScope.SUBTOPIC_MASTERY, target_id=subtopic_id
    )
    markdown = version.content_markdown
    slides = [
        LessonSlide(number=slide.number, title=slide.title, content=slide.content)
        for slide in parse_slides(markdown)
    ]
    return LessonMaterial(
        id=str(subtopic_id),
        title=version.title,
        markdown=markdown,
        slides=slides,
        progress=_progress_out(progress),
        source_material_version_id=version.id,
        quiz_unlocked=progress is not None and progress.status == MaterialProgressStatus.COMPLETED,
        quiz_id=quiz[0].id if quiz else None,
    )


async def get_quiz(session: AsyncSession, scope: Scope, topic_id: str) -> QuizMaterial:
    """Return quiz questions without joining question_answer_keys."""
    subtopic = await get_subtopic_by_slug(session, topic_id, scope=scope)
    await _covered_subtopic_node(session, scope, subtopic.id)
    released = await _released_quiz(
        session, quiz_scope=QuizScope.SUBTOPIC_MASTERY, target_id=subtopic.id
    )
    if released is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    quiz, quiz_version = released

    questions = await questions_for_quiz_version(session, quiz_version.id)
    if not questions:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Quiz for '{topic_id}' has no questions",
        )
    return QuizMaterial(
        id=quiz.id,
        title=quiz.title,
        questions=questions,
        pass_threshold_percent=quiz_version.pass_threshold_percent,
        duration_seconds=quiz_version.duration_seconds,
        max_attempts=quiz_version.max_attempts,
        result_release_mode=quiz_version.result_release_mode.value,
    )


async def questions_for_quiz_version(
    session: AsyncSession, quiz_version_id: UUID
) -> list[QuizQuestion]:
    items = (
        await session.scalars(
            select(QuizItem)
            .where(QuizItem.quiz_version_id == quiz_version_id)
            .order_by(QuizItem.sequence)
        )
    ).all()

    questions: list[QuizQuestion] = []
    for item in items:
        version = await session.scalar(
            select(QuestionVersion).where(QuestionVersion.id == item.question_version_id)
        )
        if version is None:
            continue
        options = (
            await session.scalars(
                select(QuestionOption)
                .where(QuestionOption.question_version_id == version.id)
                .order_by(QuestionOption.sequence, QuestionOption.label)
            )
        ).all()
        questions.append(
            QuizQuestion(
                number=item.sequence,
                difficulty=version.difficulty.value.title() if version.difficulty else None,
                prompt=version.prompt,
                options=[QuizOption(label=option.label, text=option.text) for option in options],
            )
        )
    return questions


async def update_material_progress(
    session: AsyncSession,
    scope: Scope,
    subtopic_id: UUID,
    payload: MaterialProgressUpdate,
) -> MaterialProgressOut:
    node = await _covered_subtopic_node(session, scope, subtopic_id)
    if scope.self_student_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Student enrollment required"
        )
    enrollment = await subject_enrollment_for(session, scope.self_student_id, node.offering.id)
    if enrollment is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Student enrollment required"
        )
    version = await _published_material_version(session, subtopic_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")
    now = datetime.now(UTC)
    progress = await _progress_for(session, enrollment.id, version.id)
    if progress is None:
        progress = StudentMaterialProgress(
            student_subject_enrollment_id=enrollment.id,
            source_material_version_id=version.id,
            status=MaterialProgressStatus.OPENED,
            opened_at=now,
            last_opened_at=now,
            last_unit_ordinal=payload.last_unit_ordinal,
        )
        session.add(progress)
    else:
        progress.last_opened_at = now
        if payload.last_unit_ordinal is not None:
            progress.last_unit_ordinal = payload.last_unit_ordinal
    if payload.status == "completed":
        progress.status = MaterialProgressStatus.COMPLETED
        progress.completed_at = progress.completed_at or now
    await session.commit()
    await session.refresh(progress)
    out = _progress_out(progress)
    assert out is not None
    return out


async def open_release_for_quiz_version(
    session: AsyncSession, quiz_version_id: UUID
) -> QuizRelease | None:
    now = datetime.now(UTC)
    return cast(
        QuizRelease | None,
        await session.scalar(
            select(QuizRelease).where(
                QuizRelease.quiz_version_id == quiz_version_id,
                QuizRelease.status == QuizReleaseStatus.OPEN,
                (QuizRelease.window_starts_at.is_(None) | (QuizRelease.window_starts_at <= now)),
                (QuizRelease.window_ends_at.is_(None) | (QuizRelease.window_ends_at >= now)),
            )
        ),
    )

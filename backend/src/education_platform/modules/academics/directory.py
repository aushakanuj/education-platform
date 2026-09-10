"""Student learning-directory composition over the academic tree.

Queries materials and assessments models/helpers directly; does not call their services.
"""

from __future__ import annotations

from uuid import UUID

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
from education_platform.modules.academics.schemas import (
    LearningDirectoryOut,
    SubjectNodeOut,
    SubtopicNodeOut,
    TopicNodeOut,
)
from education_platform.modules.assessments.models import (
    QuizAttempt,
    QuizAttemptStatus,
    QuizScope,
    QuizVersion,
)
from education_platform.modules.assessments.queries import released_quiz
from education_platform.modules.assessments.schemas import AttemptHistoryItem, QuizSummaryOut
from education_platform.modules.authorization.scope import Scope
from education_platform.modules.materials.markdown_parser import parse_slides
from education_platform.modules.materials.models import (
    MaterialProgressStatus,
    SourceMaterialVersion,
    StudentMaterialProgress,
)
from education_platform.modules.materials.queries import progress_for, published_material_version
from education_platform.modules.materials.schemas import MaterialProgressOut


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
        version = await published_material_version(session, subtopic.id)
        progress = await progress_for(
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


async def _quiz_summary(
    session: AsyncSession,
    scope: Scope,
    *,
    quiz_scope: QuizScope,
    target_id: UUID,
    unlocked: bool,
    locked_reason: str,
) -> QuizSummaryOut:
    released = await released_quiz(session, quiz_scope=quiz_scope, target_id=target_id)
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

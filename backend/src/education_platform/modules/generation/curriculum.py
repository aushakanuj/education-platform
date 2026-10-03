"""Admin ADK curriculum generation: enqueue, load, persist-after-approval."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from education_platform.core.config import get_settings
from education_platform.modules.academics.models import (
    AcademicPeriod,
    Grade,
    GradeSubjectOffering,
    LearningOutcome,
    PeriodGrade,
    Subject,
    Subtopic,
    Topic,
)
from education_platform.modules.assessments.models import (
    CommonMasteryQuiz,
    Question,
    QuestionAnswerKey,
    QuestionOption,
    QuestionOutcomeTag,
    QuestionType,
    QuestionVersion,
    QuestionVersionStatus,
    QuizItem,
    QuizMaterialBinding,
    QuizResultReleaseMode,
    QuizScope,
    QuizVersion,
    QuizVersionStatus,
)
from education_platform.modules.audit.service import record_event
from education_platform.modules.authorization.principal import Principal
from education_platform.modules.generation.adk import (
    AdkRunRequest,
    AdkRunResult,
    BankItem,
    loops_not_approved_error,
)
from education_platform.modules.generation.blueprint import (
    assemble_mastery_indexes,
    check_bank_mix,
)
from education_platform.modules.generation.items import item_scoring_rubric
from education_platform.modules.generation.lesson_checks import (
    check_lesson_quality,
    source_method_missing,
)
from education_platform.modules.generation.models import CurriculumGenerationJob
from education_platform.modules.generation.types import (
    CurriculumJob,
    GenerationError,
    GenerationJobStatus,
)
from education_platform.modules.materials.markdown_parser import title_from_markdown
from education_platform.modules.materials.models import (
    SourceChunk,
    SourceMaterial,
    SourceMaterialVersion,
    SourceMaterialVersionStatus,
)
from education_platform.modules.materials.seed_content import upsert_material_version
from education_platform.modules.materials.seed_quizzes import (
    ensure_open_release,
    seed_topic_mastery_quiz,
)

_INGESTED_VERSIONS = (
    SourceMaterialVersionStatus.READY,
    SourceMaterialVersionStatus.PUBLISHED,
)


def job_to_domain(row: CurriculumGenerationJob) -> CurriculumJob:
    return CurriculumJob(
        id=row.id,
        subtopic_id=row.subtopic_id,
        status=row.status,
        round_count=row.round_count,
        reviewer_notes=row.reviewer_notes,
        error=row.error,
        source_material_version_id=row.source_material_version_id,
        quiz_version_id=row.quiz_version_id,
    )


async def _subtopic_in_institution(
    session: AsyncSession, *, subtopic_id: UUID, institution_id: UUID
) -> Subtopic | None:
    return cast(
        Subtopic | None,
        await session.scalar(
            select(Subtopic)
            .join(Topic, Topic.id == Subtopic.topic_id)
            .join(
                GradeSubjectOffering,
                GradeSubjectOffering.id == Topic.grade_subject_offering_id,
            )
            .join(PeriodGrade, PeriodGrade.id == GradeSubjectOffering.period_grade_id)
            .join(AcademicPeriod, AcademicPeriod.id == PeriodGrade.academic_period_id)
            .where(Subtopic.id == subtopic_id, AcademicPeriod.institution_id == institution_id)
        ),
    )


async def enqueue_curriculum_generation(
    session: AsyncSession,
    principal: Principal,
    subtopic_id: UUID,
) -> CurriculumJob:
    subtopic = await _subtopic_in_institution(
        session, subtopic_id=subtopic_id, institution_id=principal.institution_id
    )
    if subtopic is None:
        raise GenerationError("Subtopic not found", status_code=404)
    job = CurriculumGenerationJob(
        subtopic_id=subtopic_id,
        status=GenerationJobStatus.QUEUED,
        created_by=principal.user_id,
        round_count=0,
    )
    session.add(job)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise GenerationError(
            "A curriculum generation job is already in progress for this subtopic.",
            status_code=409,
        ) from exc
    await record_event(
        session,
        institution_id=principal.institution_id,
        actor_user_id=principal.user_id,
        event_type="generation.curriculum_enqueued",
        entity_type="curriculum_generation_job",
        entity_id=job.id,
        payload={"subtopic_id": str(subtopic_id)},
    )
    return job_to_domain(job)


async def get_curriculum_job(
    session: AsyncSession,
    principal: Principal,
    job_id: UUID,
) -> CurriculumJob:
    row = (
        await session.execute(
            select(CurriculumGenerationJob, AcademicPeriod.institution_id)
            .join(Subtopic, Subtopic.id == CurriculumGenerationJob.subtopic_id)
            .join(Topic, Topic.id == Subtopic.topic_id)
            .join(
                GradeSubjectOffering,
                GradeSubjectOffering.id == Topic.grade_subject_offering_id,
            )
            .join(PeriodGrade, PeriodGrade.id == GradeSubjectOffering.period_grade_id)
            .join(AcademicPeriod, AcademicPeriod.id == PeriodGrade.academic_period_id)
            .where(CurriculumGenerationJob.id == job_id)
        )
    ).first()
    if row is None or row[1] != principal.institution_id:
        raise GenerationError("Generation job not found", status_code=404)
    return job_to_domain(row[0])


def ingested_chunks_for_subtopic(session: Session, subtopic_id: UUID) -> list[SourceChunk]:
    """SourceChunk rows from ingested curriculum PDFs. Seed markdown is not a source."""
    rows = list(
        session.scalars(
            select(SourceChunk)
            .join(
                SourceMaterialVersion,
                SourceMaterialVersion.id == SourceChunk.source_material_version_id,
            )
            .join(SourceMaterial, SourceMaterial.id == SourceMaterialVersion.source_material_id)
            .where(
                SourceMaterial.subtopic_id == subtopic_id,
                SourceMaterialVersion.lifecycle_status.in_(_INGESTED_VERSIONS),
            )
            .order_by(SourceChunk.ordinal, SourceChunk.created_at)
        ).all()
    )
    return [row for row in rows if row.text.strip()]


def load_generation_context(
    session: Session, subtopic_id: UUID
) -> tuple[Subtopic, str, str, tuple[str, ...]] | None:
    row = session.execute(
        select(Subtopic, Grade.name, Subject.name)
        .join(Topic, Topic.id == Subtopic.topic_id)
        .join(GradeSubjectOffering, GradeSubjectOffering.id == Topic.grade_subject_offering_id)
        .join(PeriodGrade, PeriodGrade.id == GradeSubjectOffering.period_grade_id)
        .join(Grade, Grade.id == PeriodGrade.grade_id)
        .join(Subject, Subject.id == GradeSubjectOffering.subject_id)
        .where(Subtopic.id == subtopic_id)
    ).first()
    if row is None:
        return None
    subtopic, grade_name, subject_name = row
    outcomes = tuple(
        session.scalars(
            select(LearningOutcome.statement)
            .where(LearningOutcome.subtopic_id == subtopic_id)
            .order_by(LearningOutcome.sequence)
        ).all()
    )
    return subtopic, str(grade_name), str(subject_name), outcomes


def build_adk_request(
    session: Session,
    job: CurriculumGenerationJob,
    chunks: Sequence[SourceChunk],
) -> AdkRunRequest | str:
    context = load_generation_context(session, job.subtopic_id)
    if context is None:
        return "Subtopic not found."
    subtopic, grade_name, subject_name, outcomes = context
    settings = get_settings()
    return AdkRunRequest(
        job_id=job.id,
        subtopic_id=job.subtopic_id,
        grade_name=grade_name,
        subject_name=subject_name,
        subtopic_name=subtopic.name,
        learning_outcomes=outcomes,
        source_excerpts=tuple(chunk.text for chunk in chunks),
        model=settings.adk_model,
        max_review_rounds=settings.adk_max_review_rounds,
    )


def persist_gate_error(result: AdkRunResult, lesson_markdown: str) -> str | None:
    loop_error = loops_not_approved_error(result)
    if loop_error is not None:
        return loop_error
    lesson_error = check_lesson_quality(lesson_markdown)
    if lesson_error is not None:
        return lesson_error
    missing_methods = [
        item.prompt[:40]
        for item in result.items
        if source_method_missing(lesson_markdown, item.source_method)
    ]
    if missing_methods:
        return (
            "Each quiz item must be tagged to a source method present in the lesson. "
            f"Missing methods for: {missing_methods[:5]}."
        )
    mix_error = check_bank_mix(tuple((item.item_kind, item.difficulty) for item in result.items))
    if mix_error is not None:
        return mix_error
    assembled = assemble_mastery_indexes(
        tuple((item.item_kind, item.difficulty) for item in result.items)
    )
    if isinstance(assembled, str):
        return assembled
    return None


def _primary_outcome_id(session: Session, subtopic_id: UUID) -> UUID | None:
    return session.scalar(
        select(LearningOutcome.id)
        .where(LearningOutcome.subtopic_id == subtopic_id)
        .order_by(LearningOutcome.sequence)
    )


def _persist_bank_item(
    session: Session,
    *,
    subtopic_id: UUID,
    item: BankItem,
    outcome_id: UUID | None,
) -> QuestionVersion:
    question = Question(subtopic_id=subtopic_id)
    session.add(question)
    session.flush()
    version = QuestionVersion(
        question_id=question.id,
        version_number=1,
        prompt=item.prompt,
        question_type=QuestionType.MULTIPLE_CHOICE,
        difficulty=item.difficulty,
        item_kind=item.item_kind,
        explanation=item.explanation or None,
        lifecycle_status=QuestionVersionStatus.PUBLISHED,
    )
    session.add(version)
    session.flush()
    for sequence, label in enumerate(("A", "B", "C", "D")):
        session.add(
            QuestionOption(
                question_version_id=version.id,
                label=label,
                text=item.options[label],
                sequence=sequence,
            )
        )
    session.add(
        QuestionAnswerKey(
            question_version_id=version.id,
            correct_option_label=item.correct_label,
            correct_rationale=item.explanation or None,
            distractor_rationales=dict(item.distractor_rationales) or None,
            scoring_rubric=item_scoring_rubric(item.bloom, item.misconception_labels),
        )
    )
    if outcome_id is not None:
        session.add(
            QuestionOutcomeTag(question_version_id=version.id, learning_outcome_id=outcome_id)
        )
    return version


def _next_quiz_version_number(session: Session, quiz_id: UUID) -> int:
    current = session.scalar(
        select(func.max(QuizVersion.version_number)).where(QuizVersion.quiz_id == quiz_id)
    )
    return int(current or 0) + 1


def persist_approved_curriculum(
    session: Session,
    job: CurriculumGenerationJob,
    result: AdkRunResult,
) -> str | None:
    """Write lesson + 80-item bank + 10-item quiz. Returns an error if the gate fails."""
    gate = persist_gate_error(result, result.lesson_markdown)
    if gate is not None:
        return gate
    assembled = assemble_mastery_indexes(
        tuple((item.item_kind, item.difficulty) for item in result.items)
    )
    if isinstance(assembled, str):
        return assembled
    subtopic = session.get(Subtopic, job.subtopic_id)
    if subtopic is None:
        return "Subtopic not found."
    title = title_from_markdown(result.lesson_markdown, subtopic.slug)
    material_version = upsert_material_version(
        session, subtopic, title=title, markdown=result.lesson_markdown
    )
    outcome_id = _primary_outcome_id(session, subtopic.id)
    versions = [
        _persist_bank_item(session, subtopic_id=subtopic.id, item=item, outcome_id=outcome_id)
        for item in result.items
    ]
    mastery = session.scalar(
        select(CommonMasteryQuiz).where(
            CommonMasteryQuiz.subtopic_id == subtopic.id,
            CommonMasteryQuiz.quiz_scope == QuizScope.SUBTOPIC_MASTERY,
        )
    )
    if mastery is None:
        mastery = CommonMasteryQuiz(
            quiz_scope=QuizScope.SUBTOPIC_MASTERY,
            subtopic_id=subtopic.id,
            title=f"{subtopic.name} quiz",
        )
        session.add(mastery)
        session.flush()
    quiz_version = QuizVersion(
        quiz_id=mastery.id,
        version_number=_next_quiz_version_number(session, mastery.id),
        lifecycle_status=QuizVersionStatus.RELEASED,
        result_release_mode=QuizResultReleaseMode.IMMEDIATE,
        pass_threshold_percent=get_settings().mastery_pass_percent,
        released_at=datetime.now(UTC),
    )
    session.add(quiz_version)
    session.flush()
    ensure_open_release(session, quiz_version)
    session.add(
        QuizMaterialBinding(
            quiz_version_id=quiz_version.id,
            source_material_version_id=material_version.id,
        )
    )
    for sequence, index in enumerate(assembled, start=1):
        session.add(
            QuizItem(
                quiz_version_id=quiz_version.id,
                question_version_id=versions[index].id,
                sequence=sequence,
            )
        )
    topic = session.get(Topic, subtopic.topic_id)
    if topic is not None:
        seed_topic_mastery_quiz(session, topic)
    job.source_material_version_id = material_version.id
    job.quiz_version_id = quiz_version.id
    job.reviewer_notes = result.reviewer_notes or None
    job.round_count = result.round_count
    job.transcript = result.transcript
    job.error = None
    job.status = GenerationJobStatus.SUCCEEDED
    return None


def fail_curriculum_job(
    job: CurriculumGenerationJob, reason: str, *, result: AdkRunResult | None = None
) -> None:
    job.status = GenerationJobStatus.FAILED
    job.error = reason[:2000]
    if result is not None:
        job.reviewer_notes = result.reviewer_notes or job.reviewer_notes
        job.round_count = result.round_count
        job.transcript = result.transcript
    job.source_material_version_id = None
    job.quiz_version_id = None

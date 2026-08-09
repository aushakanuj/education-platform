"""Materials catalog and content reads from SQLite."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.api.deps import Principal
from education_platform.modules.academics.models import Subtopic
from education_platform.modules.academics.service import assert_can_access_subtopic
from education_platform.modules.assessments.models import (
    CommonMasteryQuiz,
    QuestionOption,
    QuestionVersion,
    QuizItem,
    QuizVersion,
    QuizVersionStatus,
)
from education_platform.modules.materials.markdown_parser import parse_slides
from education_platform.modules.materials.models import (
    SourceMaterial,
    SourceMaterialVersion,
    SourceMaterialVersionStatus,
)
from education_platform.modules.materials.schemas import (
    LessonMaterial,
    LessonSlide,
    QuizMaterial,
    QuizOption,
    QuizQuestion,
    TopicSummary,
)


async def list_topics(session: AsyncSession, principal: Principal) -> list[TopicSummary]:
    subtopics = (
        await session.scalars(select(Subtopic).order_by(Subtopic.sequence, Subtopic.slug))
    ).all()
    topics: list[TopicSummary] = []
    for subtopic in subtopics:
        try:
            await assert_can_access_subtopic(session, principal, subtopic.id)
        except HTTPException:
            continue
        has_lesson = await session.scalar(
            select(func.count())
            .select_from(SourceMaterialVersion)
            .join(SourceMaterial, SourceMaterial.id == SourceMaterialVersion.source_material_id)
            .where(
                SourceMaterial.subtopic_id == subtopic.id,
                SourceMaterialVersion.lifecycle_status == SourceMaterialVersionStatus.PUBLISHED,
            )
        )
        has_quiz = await session.scalar(
            select(func.count())
            .select_from(QuizVersion)
            .join(CommonMasteryQuiz, CommonMasteryQuiz.id == QuizVersion.quiz_id)
            .where(
                CommonMasteryQuiz.subtopic_id == subtopic.id,
                QuizVersion.lifecycle_status == QuizVersionStatus.RELEASED,
            )
        )
        if not has_lesson and not has_quiz:
            continue
        topics.append(
            TopicSummary(
                id=subtopic.slug,
                title=subtopic.name,
                has_lesson=bool(has_lesson),
                has_quiz=bool(has_quiz),
            )
        )
    return topics


async def get_subtopic_by_slug(session: AsyncSession, topic_id: str) -> Subtopic:
    subtopic = await session.scalar(select(Subtopic).where(Subtopic.slug == topic_id))
    if subtopic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Topic '{topic_id}' not found",
        )
    return subtopic


# Back-compat alias used by assessments service.
_get_subtopic = get_subtopic_by_slug


async def get_lesson(session: AsyncSession, principal: Principal, topic_id: str) -> LessonMaterial:
    subtopic = await get_subtopic_by_slug(session, topic_id)
    await assert_can_access_subtopic(session, principal, subtopic.id)
    version = await session.scalar(
        select(SourceMaterialVersion)
        .join(SourceMaterial, SourceMaterial.id == SourceMaterialVersion.source_material_id)
        .where(
            SourceMaterial.subtopic_id == subtopic.id,
            SourceMaterialVersion.lifecycle_status == SourceMaterialVersionStatus.PUBLISHED,
        )
        .order_by(SourceMaterialVersion.version_number.desc())
    )
    if version is None or not version.content_markdown:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lesson not found for topic '{topic_id}'",
        )
    markdown = version.content_markdown
    slides = [
        LessonSlide(number=slide.number, title=slide.title, content=slide.content)
        for slide in parse_slides(markdown)
    ]
    return LessonMaterial(
        id=topic_id,
        title=version.title,
        markdown=markdown,
        slides=slides,
    )


async def get_quiz(session: AsyncSession, principal: Principal, topic_id: str) -> QuizMaterial:
    """Return quiz questions without joining question_answer_keys."""
    subtopic = await get_subtopic_by_slug(session, topic_id)
    await assert_can_access_subtopic(session, principal, subtopic.id)
    quiz = await session.scalar(
        select(CommonMasteryQuiz).where(CommonMasteryQuiz.subtopic_id == subtopic.id)
    )
    if quiz is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quiz not found for topic '{topic_id}'",
        )

    quiz_version = await session.scalar(
        select(QuizVersion)
        .where(
            QuizVersion.quiz_id == quiz.id,
            QuizVersion.lifecycle_status == QuizVersionStatus.RELEASED,
        )
        .order_by(QuizVersion.version_number.desc())
    )
    if quiz_version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quiz not found for topic '{topic_id}'",
        )

    items = (
        await session.scalars(
            select(QuizItem)
            .where(QuizItem.quiz_version_id == quiz_version.id)
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

    if not questions:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Quiz for '{topic_id}' has no questions",
        )

    return QuizMaterial(id=topic_id, title=quiz.title, questions=questions)

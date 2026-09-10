"""Quiz seed helpers for subtopic and topic mastery quizzes."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from education_platform.core.config import get_settings
from education_platform.modules.academics.models import LearningOutcome, Subtopic, Topic
from education_platform.modules.assessments.models import (
    CommonMasteryQuiz,
    Question,
    QuestionAnswerKey,
    QuestionDifficulty,
    QuestionOption,
    QuestionOutcomeTag,
    QuestionType,
    QuestionVersion,
    QuestionVersionStatus,
    QuizItem,
    QuizMaterialBinding,
    QuizRelease,
    QuizReleaseStatus,
    QuizResultReleaseMode,
    QuizScope,
    QuizVersion,
    QuizVersionStatus,
)
from education_platform.modules.materials.markdown_parser import ParsedQuiz
from education_platform.modules.materials.models import SourceMaterialVersion

DIFFICULTY = {
    "easy": QuestionDifficulty.EASY,
    "medium": QuestionDifficulty.MEDIUM,
    "hard": QuestionDifficulty.HARD,
}


def ensure_open_release(session: Session, quiz_version: QuizVersion) -> None:
    release = session.scalar(
        select(QuizRelease).where(
            QuizRelease.quiz_version_id == quiz_version.id,
            QuizRelease.status == QuizReleaseStatus.OPEN,
        )
    )
    if release is None:
        session.add(
            QuizRelease(
                quiz_version_id=quiz_version.id,
                status=QuizReleaseStatus.OPEN,
                released_by_user_id=None,
            )
        )


def latest_released_quiz_version(session: Session, quiz_id: object) -> QuizVersion | None:
    return session.scalar(
        select(QuizVersion)
        .where(
            QuizVersion.quiz_id == quiz_id,
            QuizVersion.lifecycle_status == QuizVersionStatus.RELEASED,
        )
        .order_by(QuizVersion.version_number.desc())
    )


def quiz_version_matches(
    session: Session, quiz_version: QuizVersion, quiz_data: ParsedQuiz
) -> bool:
    items = session.scalars(
        select(QuizItem)
        .where(QuizItem.quiz_version_id == quiz_version.id)
        .order_by(QuizItem.sequence)
    ).all()
    questions = quiz_data.questions
    if len(items) != len(questions):
        return False
    for item, parsed in zip(items, questions, strict=True):
        version = session.get(QuestionVersion, item.question_version_id)
        if version is None or version.prompt != parsed.prompt:
            return False
        options = session.scalars(
            select(QuestionOption)
            .where(QuestionOption.question_version_id == version.id)
            .order_by(QuestionOption.sequence)
        ).all()
        if [(o.label, o.text) for o in options] != [(o.label, o.text) for o in parsed.options]:
            return False
        key = session.scalar(
            select(QuestionAnswerKey).where(QuestionAnswerKey.question_version_id == version.id)
        )
        if key is None or key.correct_option_label != parsed.correct_option_label:
            return False
    return True


def upsert_subtopic_quiz(
    session: Session,
    subtopic: Subtopic,
    outcome: LearningOutcome,
    quiz_data: ParsedQuiz,
    material_version: SourceMaterialVersion | None,
) -> QuizVersion:
    mastery_quiz = session.scalar(
        select(CommonMasteryQuiz).where(
            CommonMasteryQuiz.subtopic_id == subtopic.id,
            CommonMasteryQuiz.quiz_scope == QuizScope.SUBTOPIC_MASTERY,
        )
    )
    if mastery_quiz is None:
        mastery_quiz = CommonMasteryQuiz(
            quiz_scope=QuizScope.SUBTOPIC_MASTERY,
            subtopic_id=subtopic.id,
            title=quiz_data.title,
        )
        session.add(mastery_quiz)
        session.flush()
    else:
        mastery_quiz.title = quiz_data.title

    existing = latest_released_quiz_version(session, mastery_quiz.id)
    if existing is not None and quiz_version_matches(session, existing, quiz_data):
        ensure_open_release(session, existing)
        return existing

    next_version = (
        int(
            session.scalar(
                select(func.max(QuizVersion.version_number)).where(
                    QuizVersion.quiz_id == mastery_quiz.id
                )
            )
            or 0
        )
        + 1
    )
    quiz_version = QuizVersion(
        quiz_id=mastery_quiz.id,
        version_number=next_version,
        lifecycle_status=QuizVersionStatus.RELEASED,
        result_release_mode=QuizResultReleaseMode.IMMEDIATE,
        pass_threshold_percent=get_settings().mastery_pass_percent,
        released_at=datetime.now(UTC),
    )
    session.add(quiz_version)
    session.flush()
    ensure_open_release(session, quiz_version)

    if material_version is not None:
        session.add(
            QuizMaterialBinding(
                quiz_version_id=quiz_version.id,
                source_material_version_id=material_version.id,
            )
        )

    for question_data in quiz_data.questions:
        question = Question(subtopic_id=subtopic.id, code=f"Q{question_data.number}")
        session.add(question)
        session.flush()
        difficulty = None
        if question_data.difficulty:
            difficulty = DIFFICULTY.get(question_data.difficulty.lower())
        version = QuestionVersion(
            question_id=question.id,
            version_number=1,
            prompt=question_data.prompt,
            question_type=QuestionType.MULTIPLE_CHOICE,
            difficulty=difficulty,
            explanation=question_data.explanation,
            lifecycle_status=QuestionVersionStatus.PUBLISHED,
        )
        session.add(version)
        session.flush()
        for index, option in enumerate(question_data.options, start=1):
            session.add(
                QuestionOption(
                    question_version_id=version.id,
                    label=option.label,
                    text=option.text,
                    sequence=index,
                )
            )
        session.add(
            QuestionAnswerKey(
                question_version_id=version.id,
                correct_option_label=question_data.correct_option_label,
            )
        )
        session.add(
            QuestionOutcomeTag(question_version_id=version.id, learning_outcome_id=outcome.id)
        )
        session.add(
            QuizItem(
                quiz_version_id=quiz_version.id,
                question_version_id=version.id,
                sequence=question_data.number,
            )
        )
    return quiz_version


def seed_topic_mastery_quiz(session: Session, parent_topic: Topic) -> None:
    subtopics = session.scalars(
        select(Subtopic)
        .where(Subtopic.topic_id == parent_topic.id)
        .order_by(Subtopic.sequence, Subtopic.slug)
    ).all()
    source_items: list[QuizItem] = []
    for subtopic in subtopics:
        quiz = session.scalar(
            select(CommonMasteryQuiz).where(
                CommonMasteryQuiz.subtopic_id == subtopic.id,
                CommonMasteryQuiz.quiz_scope == QuizScope.SUBTOPIC_MASTERY,
            )
        )
        if quiz is None:
            continue
        version = latest_released_quiz_version(session, quiz.id)
        if version is None:
            continue
        source_items.extend(
            session.scalars(
                select(QuizItem)
                .where(QuizItem.quiz_version_id == version.id)
                .order_by(QuizItem.sequence)
            ).all()
        )
    if not source_items:
        return

    quiz = session.scalar(
        select(CommonMasteryQuiz).where(
            CommonMasteryQuiz.topic_id == parent_topic.id,
            CommonMasteryQuiz.quiz_scope == QuizScope.TOPIC_MASTERY,
        )
    )
    if quiz is None:
        quiz = CommonMasteryQuiz(
            quiz_scope=QuizScope.TOPIC_MASTERY,
            topic_id=parent_topic.id,
            title="Approved Materials Overall Quiz",
        )
        session.add(quiz)
        session.flush()
    else:
        quiz.title = "Approved Materials Overall Quiz"

    latest = latest_released_quiz_version(session, quiz.id)
    latest_ids = []
    if latest is not None:
        latest_ids = [
            item.question_version_id
            for item in session.scalars(
                select(QuizItem)
                .where(QuizItem.quiz_version_id == latest.id)
                .order_by(QuizItem.sequence)
            ).all()
        ]
    source_ids = [item.question_version_id for item in source_items]
    if latest is not None and latest_ids == source_ids:
        ensure_open_release(session, latest)
        return

    next_version = (
        int(
            session.scalar(
                select(func.max(QuizVersion.version_number)).where(QuizVersion.quiz_id == quiz.id)
            )
            or 0
        )
        + 1
    )
    version = QuizVersion(
        quiz_id=quiz.id,
        version_number=next_version,
        lifecycle_status=QuizVersionStatus.RELEASED,
        result_release_mode=QuizResultReleaseMode.IMMEDIATE,
        pass_threshold_percent=get_settings().mastery_pass_percent,
        released_at=datetime.now(UTC),
    )
    session.add(version)
    session.flush()
    ensure_open_release(session, version)
    for sequence, item in enumerate(source_items, start=1):
        session.add(
            QuizItem(
                quiz_version_id=version.id,
                question_version_id=item.question_version_id,
                sequence=sequence,
            )
        )

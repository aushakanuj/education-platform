"""Import approved markdown curriculum from docs/materials into SQLite."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from education_platform.core.config import get_settings
from education_platform.modules.academics.models import (
    AcademicPeriod,
    AcademicPeriodStatus,
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
    QuestionDifficulty,
    QuestionOption,
    QuestionOutcomeTag,
    QuestionType,
    QuestionVersion,
    QuestionVersionStatus,
    QuizItem,
    QuizMaterialBinding,
    QuizResultReleaseMode,
    QuizVersion,
    QuizVersionStatus,
)
from education_platform.modules.auth.models import Institution, InstitutionStatus
from education_platform.modules.materials.markdown_parser import parse_lesson, parse_quiz
from education_platform.modules.materials.models import (
    SourceMaterial,
    SourceMaterialStatus,
    SourceMaterialVersion,
    SourceMaterialVersionStatus,
)

POC_INSTITUTION_NAME = "POC Demo School"
POC_PERIOD_NAME = "2026-27"
POC_GRADE_NAME = "Grade 8"
POC_SUBJECT_CODE = "MATH"
POC_TOPIC_SLUG = "approved_materials"

_LESSON_SUFFIX = "_lesson.md"
_QUIZ_SUFFIX = "_quiz.md"

_DIFFICULTY = {
    "easy": QuestionDifficulty.EASY,
    "medium": QuestionDifficulty.MEDIUM,
    "hard": QuestionDifficulty.HARD,
}


def discover_topic_ids(materials_dir: Path) -> list[str]:
    topic_ids: set[str] = set()
    for path in materials_dir.glob("*.md"):
        name = path.name
        if name.endswith(_LESSON_SUFFIX):
            topic_ids.add(name[: -len(_LESSON_SUFFIX)])
        elif name.endswith(_QUIZ_SUFFIX):
            topic_ids.add(name[: -len(_QUIZ_SUFFIX)])
    return sorted(topic_ids)


def _ensure_curriculum_root(session: Session) -> Topic:
    """Return the parent Topic that holds approved-material subtopics."""
    institution = session.scalar(
        select(Institution).where(Institution.name == POC_INSTITUTION_NAME)
    )
    if institution is None:
        institution = Institution(
            name=POC_INSTITUTION_NAME,
            timezone="UTC",
            status=InstitutionStatus.ACTIVE,
        )
        session.add(institution)
        session.flush()

    period = session.scalar(
        select(AcademicPeriod).where(
            AcademicPeriod.institution_id == institution.id,
            AcademicPeriod.name == POC_PERIOD_NAME,
        )
    )
    if period is None:
        period = AcademicPeriod(
            institution_id=institution.id,
            name=POC_PERIOD_NAME,
            start_date=date(2026, 6, 1),
            end_date=date(2027, 3, 31),
            status=AcademicPeriodStatus.ACTIVE,
        )
        session.add(period)
        session.flush()
    elif period.status != AcademicPeriodStatus.ACTIVE:
        period.status = AcademicPeriodStatus.ACTIVE

    grade = session.scalar(
        select(Grade).where(
            Grade.institution_id == institution.id,
            Grade.name == POC_GRADE_NAME,
        )
    )
    if grade is None:
        grade = Grade(institution_id=institution.id, name=POC_GRADE_NAME, sort_order=8)
        session.add(grade)
        session.flush()

    subject = session.scalar(
        select(Subject).where(
            Subject.institution_id == institution.id,
            Subject.code == POC_SUBJECT_CODE,
        )
    )
    if subject is None:
        subject = Subject(
            institution_id=institution.id,
            name="Mathematics",
            code=POC_SUBJECT_CODE,
        )
        session.add(subject)
        session.flush()

    period_grade = session.scalar(
        select(PeriodGrade).where(
            PeriodGrade.academic_period_id == period.id,
            PeriodGrade.grade_id == grade.id,
        )
    )
    if period_grade is None:
        period_grade = PeriodGrade(academic_period_id=period.id, grade_id=grade.id)
        session.add(period_grade)
        session.flush()

    offering = session.scalar(
        select(GradeSubjectOffering).where(
            GradeSubjectOffering.period_grade_id == period_grade.id,
            GradeSubjectOffering.subject_id == subject.id,
        )
    )
    if offering is None:
        offering = GradeSubjectOffering(period_grade_id=period_grade.id, subject_id=subject.id)
        session.add(offering)
        session.flush()

    topic = session.scalar(
        select(Topic).where(
            Topic.grade_subject_offering_id == offering.id,
            Topic.slug == POC_TOPIC_SLUG,
        )
    )
    if topic is None:
        topic = Topic(
            grade_subject_offering_id=offering.id,
            name="Approved Materials",
            slug=POC_TOPIC_SLUG,
            sequence=1,
        )
        session.add(topic)
        session.flush()
    return topic


def _clear_subtopic_content(session: Session, subtopic: Subtopic) -> None:
    quiz = session.scalar(
        select(CommonMasteryQuiz).where(CommonMasteryQuiz.subtopic_id == subtopic.id)
    )
    if quiz is not None:
        quiz_versions = session.scalars(
            select(QuizVersion).where(QuizVersion.quiz_id == quiz.id)
        ).all()
        for quiz_version in quiz_versions:
            session.execute(delete(QuizItem).where(QuizItem.quiz_version_id == quiz_version.id))
            session.execute(
                delete(QuizMaterialBinding).where(
                    QuizMaterialBinding.quiz_version_id == quiz_version.id
                )
            )
            session.delete(quiz_version)
        session.delete(quiz)

    questions = session.scalars(select(Question).where(Question.subtopic_id == subtopic.id)).all()
    for question in questions:
        question_versions = session.scalars(
            select(QuestionVersion).where(QuestionVersion.question_id == question.id)
        ).all()
        for question_version in question_versions:
            session.execute(
                delete(QuestionOption).where(
                    QuestionOption.question_version_id == question_version.id
                )
            )
            session.execute(
                delete(QuestionAnswerKey).where(
                    QuestionAnswerKey.question_version_id == question_version.id
                )
            )
            session.execute(
                delete(QuestionOutcomeTag).where(
                    QuestionOutcomeTag.question_version_id == question_version.id
                )
            )
            session.delete(question_version)
        session.delete(question)

    materials = session.scalars(
        select(SourceMaterial).where(SourceMaterial.subtopic_id == subtopic.id)
    ).all()
    for material in materials:
        material_versions = session.scalars(
            select(SourceMaterialVersion).where(
                SourceMaterialVersion.source_material_id == material.id
            )
        ).all()
        for material_version in material_versions:
            session.delete(material_version)
        session.delete(material)

    outcomes = session.scalars(
        select(LearningOutcome).where(LearningOutcome.subtopic_id == subtopic.id)
    ).all()
    for outcome in outcomes:
        session.delete(outcome)


def _seed_subtopic(
    session: Session,
    parent_topic: Topic,
    topic_id: str,
    sequence: int,
    materials_dir: Path,
) -> None:
    lesson_path = materials_dir / f"{topic_id}{_LESSON_SUFFIX}"
    quiz_path = materials_dir / f"{topic_id}{_QUIZ_SUFFIX}"
    if not lesson_path.is_file() and not quiz_path.is_file():
        return

    title_fallback = topic_id.replace("_", " ").title()
    display_title = title_fallback
    if lesson_path.is_file():
        display_title = parse_lesson(lesson_path.read_text(encoding="utf-8"), topic_id).title
    elif quiz_path.is_file():
        display_title = parse_quiz(quiz_path.read_text(encoding="utf-8"), topic_id).title

    subtopic = session.scalar(
        select(Subtopic).where(Subtopic.topic_id == parent_topic.id, Subtopic.slug == topic_id)
    )
    if subtopic is None:
        subtopic = Subtopic(
            topic_id=parent_topic.id,
            name=display_title,
            slug=topic_id,
            sequence=sequence,
        )
        session.add(subtopic)
        session.flush()
    else:
        subtopic.name = display_title
        subtopic.sequence = sequence
        _clear_subtopic_content(session, subtopic)
        session.flush()

    outcome = LearningOutcome(
        subtopic_id=subtopic.id,
        code="LO1",
        statement=f"Demonstrate understanding of {display_title}",
        sequence=1,
    )
    session.add(outcome)
    session.flush()

    published_material_version: SourceMaterialVersion | None = None
    if lesson_path.is_file():
        lesson = parse_lesson(lesson_path.read_text(encoding="utf-8"), topic_id)
        material = SourceMaterial(
            subtopic_id=subtopic.id,
            title=lesson.title,
            slug="lesson",
            status=SourceMaterialStatus.PUBLISHED,
        )
        session.add(material)
        session.flush()
        published_material_version = SourceMaterialVersion(
            source_material_id=material.id,
            version_number=1,
            lifecycle_status=SourceMaterialVersionStatus.PUBLISHED,
            title=lesson.title,
            content_markdown=lesson.markdown,
            content_format="markdown",
            published_at=datetime.now(UTC),
        )
        session.add(published_material_version)
        session.flush()

    if quiz_path.is_file():
        quiz = parse_quiz(quiz_path.read_text(encoding="utf-8"), topic_id)
        mastery_quiz = CommonMasteryQuiz(subtopic_id=subtopic.id, title=quiz.title)
        session.add(mastery_quiz)
        session.flush()
        quiz_version = QuizVersion(
            quiz_id=mastery_quiz.id,
            version_number=1,
            lifecycle_status=QuizVersionStatus.RELEASED,
            result_release_mode=QuizResultReleaseMode.IMMEDIATE,
            released_at=datetime.now(UTC),
        )
        session.add(quiz_version)
        session.flush()

        if published_material_version is not None:
            session.add(
                QuizMaterialBinding(
                    quiz_version_id=quiz_version.id,
                    source_material_version_id=published_material_version.id,
                )
            )

        for question_data in quiz.questions:
            question = Question(subtopic_id=subtopic.id, code=f"Q{question_data.number}")
            session.add(question)
            session.flush()
            difficulty = None
            if question_data.difficulty:
                difficulty = _DIFFICULTY.get(question_data.difficulty.lower())
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
                QuestionOutcomeTag(
                    question_version_id=version.id,
                    learning_outcome_id=outcome.id,
                )
            )
            session.add(
                QuizItem(
                    quiz_version_id=quiz_version.id,
                    question_version_id=version.id,
                    sequence=question_data.number,
                )
            )


def seed_approved_materials(
    session: Session,
    materials_dir: Path | None = None,
    *,
    replace: bool = True,
) -> list[str]:
    """Load markdown curriculum into the relational schema.

    Returns the topic ids (subtopic slugs) that were seeded.
    """
    directory = materials_dir or get_settings().materials_dir
    if not directory.is_dir():
        raise FileNotFoundError(f"Materials directory not found: {directory}")

    topic_ids = discover_topic_ids(directory)
    if not topic_ids:
        return []

    parent_topic = _ensure_curriculum_root(session)

    if not replace:
        existing = {
            slug
            for slug in session.scalars(
                select(Subtopic.slug).where(Subtopic.topic_id == parent_topic.id)
            ).all()
        }
        topic_ids = [topic_id for topic_id in topic_ids if topic_id not in existing]
        if not topic_ids:
            return []

    for sequence, topic_id in enumerate(topic_ids, start=1):
        _seed_subtopic(session, parent_topic, topic_id, sequence, directory)

    session.commit()
    return topic_ids


def main() -> None:
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import Session as SyncSession

    settings = get_settings()
    url = settings.database_url.replace("+aiosqlite", "")
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    with SyncSession(engine) as session:
        seeded = seed_approved_materials(session, replace=True)
    engine.dispose()
    print(f"Seeded topics: {', '.join(seeded) if seeded else '(none)'}")


if __name__ == "__main__":
    main()

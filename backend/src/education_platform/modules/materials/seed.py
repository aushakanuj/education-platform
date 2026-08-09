"""Import approved markdown curriculum from docs/materials into SQLite."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from education_platform.core.config import get_settings
from education_platform.modules.academics.models import (
    AcademicPeriod,
    AcademicPeriodStatus,
    EnrollmentStatus,
    Grade,
    GradeSubjectOffering,
    LearningOutcome,
    PeriodGrade,
    StudentGradeEnrollment,
    StudentSubjectEnrollment,
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
    QuizAttempt,
    QuizItem,
    QuizMaterialBinding,
    QuizRelease,
    QuizReleaseStatus,
    QuizResultReleaseMode,
    QuizScope,
    QuizVersion,
    QuizVersionStatus,
)
from education_platform.modules.auth.models import (
    Institution,
    InstitutionStatus,
    RoleName,
    StudentProfile,
    StudentProfileStatus,
    User,
    UserRole,
    UserStatus,
)
from education_platform.modules.auth.security import hash_password
from education_platform.modules.materials.markdown_parser import (
    ParsedQuiz,
    parse_lesson,
    parse_objectives_from_lesson,
    parse_quiz,
)
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


def _checksum(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


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


def _ensure_open_release(session: Session, quiz_version: QuizVersion) -> None:
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


def _ensure_outcomes(
    session: Session,
    subtopic: Subtopic,
    statements: list[str],
    *,
    display_title: str,
) -> LearningOutcome:
    cleaned = [item.strip() for item in statements if item.strip()]
    if not cleaned:
        cleaned = [f"Demonstrate understanding of {display_title}"]

    primary: LearningOutcome | None = None
    for index, statement in enumerate(cleaned, start=1):
        code = f"LO{index}"
        outcome = session.scalar(
            select(LearningOutcome).where(
                LearningOutcome.subtopic_id == subtopic.id,
                LearningOutcome.code == code,
            )
        )
        if outcome is None:
            outcome = LearningOutcome(
                subtopic_id=subtopic.id,
                code=code,
                statement=statement,
                sequence=index,
            )
            session.add(outcome)
            session.flush()
        else:
            outcome.statement = statement
            outcome.sequence = index
        if primary is None:
            primary = outcome

    assert primary is not None
    return primary


def _upsert_material_version(
    session: Session,
    subtopic: Subtopic,
    *,
    title: str,
    markdown: str,
) -> SourceMaterialVersion:
    material = session.scalar(
        select(SourceMaterial).where(
            SourceMaterial.subtopic_id == subtopic.id,
            SourceMaterial.slug == "lesson",
        )
    )
    if material is None:
        material = SourceMaterial(
            subtopic_id=subtopic.id,
            title=title,
            slug="lesson",
            status=SourceMaterialStatus.PUBLISHED,
        )
        session.add(material)
        session.flush()
    else:
        material.title = title
        material.status = SourceMaterialStatus.PUBLISHED

    checksum = _checksum(markdown)
    published = session.scalar(
        select(SourceMaterialVersion).where(
            SourceMaterialVersion.source_material_id == material.id,
            SourceMaterialVersion.lifecycle_status == SourceMaterialVersionStatus.PUBLISHED,
        )
    )
    if published is not None and published.checksum == checksum:
        return published
    if published is not None:
        published.lifecycle_status = SourceMaterialVersionStatus.SUPERSEDED

    next_version = (
        int(
            session.scalar(
                select(func.max(SourceMaterialVersion.version_number)).where(
                    SourceMaterialVersion.source_material_id == material.id
                )
            )
            or 0
        )
        + 1
    )
    version = SourceMaterialVersion(
        source_material_id=material.id,
        version_number=next_version,
        lifecycle_status=SourceMaterialVersionStatus.PUBLISHED,
        title=title,
        content_markdown=markdown,
        content_format="markdown",
        checksum=checksum,
        published_at=datetime.now(UTC),
    )
    session.add(version)
    session.flush()
    return version


def _latest_released_quiz_version(session: Session, quiz_id: object) -> QuizVersion | None:
    return session.scalar(
        select(QuizVersion)
        .where(
            QuizVersion.quiz_id == quiz_id,
            QuizVersion.lifecycle_status == QuizVersionStatus.RELEASED,
        )
        .order_by(QuizVersion.version_number.desc())
    )


def _quiz_version_matches(
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


def _upsert_subtopic_quiz(
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

    existing = _latest_released_quiz_version(session, mastery_quiz.id)
    if existing is not None and _quiz_version_matches(session, existing, quiz_data):
        _ensure_open_release(session, existing)
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
    _ensure_open_release(session, quiz_version)

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
        session.flush()

    outcome_statements: list[str] = []
    published_material_version: SourceMaterialVersion | None = None
    if lesson_path.is_file():
        lesson = parse_lesson(lesson_path.read_text(encoding="utf-8"), topic_id)
        outcome_statements = parse_objectives_from_lesson(lesson.markdown)
        published_material_version = _upsert_material_version(
            session, subtopic, title=lesson.title, markdown=lesson.markdown
        )

    outcome = _ensure_outcomes(session, subtopic, outcome_statements, display_title=display_title)

    if quiz_path.is_file():
        quiz = parse_quiz(quiz_path.read_text(encoding="utf-8"), topic_id)
        _upsert_subtopic_quiz(session, subtopic, outcome, quiz, published_material_version)


def _seed_topic_mastery_quiz(session: Session, parent_topic: Topic) -> None:
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
        version = _latest_released_quiz_version(session, quiz.id)
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

    latest = _latest_released_quiz_version(session, quiz.id)
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
        _ensure_open_release(session, latest)
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
    _ensure_open_release(session, version)
    for sequence, item in enumerate(source_items, start=1):
        session.add(
            QuizItem(
                quiz_version_id=version.id,
                question_version_id=item.question_version_id,
                sequence=sequence,
            )
        )


def _attempts_exist(session: Session) -> bool:
    return bool(session.scalar(select(QuizAttempt.id).limit(1)))


def seed_demo_student(session: Session) -> None:
    settings = get_settings()
    if not settings.is_development:
        return
    institution = session.scalar(
        select(Institution).where(Institution.name == POC_INSTITUTION_NAME)
    )
    if institution is None:
        return
    email = settings.demo_student_email.lower()
    user = session.scalar(
        select(User).where(User.institution_id == institution.id, User.email == email)
    )
    if user is None:
        user = User(
            institution_id=institution.id,
            email=email,
            full_name="Asha Student",
            password_hash=hash_password(settings.demo_student_password),
            status=UserStatus.ACTIVE,
        )
        session.add(user)
        session.flush()
    else:
        user.status = UserStatus.ACTIVE
        user.full_name = "Asha Student"
        user.password_hash = hash_password(settings.demo_student_password)
    if (
        session.scalar(
            select(UserRole).where(UserRole.user_id == user.id, UserRole.role == RoleName.STUDENT)
        )
        is None
    ):
        session.add(UserRole(user_id=user.id, role=RoleName.STUDENT))

    profile = session.scalar(
        select(StudentProfile).where(
            StudentProfile.institution_id == institution.id,
            StudentProfile.student_identifier == "DEMO-001",
        )
    )
    if profile is None:
        profile = StudentProfile(
            institution_id=institution.id,
            user_id=user.id,
            student_identifier="DEMO-001",
            full_name="Demo Student",
            status=StudentProfileStatus.ACTIVE,
        )
        session.add(profile)
        session.flush()
    else:
        profile.user_id = user.id
        profile.status = StudentProfileStatus.ACTIVE

    period = session.scalar(
        select(AcademicPeriod).where(
            AcademicPeriod.institution_id == institution.id,
            AcademicPeriod.name == POC_PERIOD_NAME,
        )
    )
    grade = session.scalar(
        select(Grade).where(Grade.institution_id == institution.id, Grade.name == POC_GRADE_NAME)
    )
    subject = session.scalar(
        select(Subject).where(
            Subject.institution_id == institution.id, Subject.code == POC_SUBJECT_CODE
        )
    )
    if period is None or grade is None or subject is None:
        return
    period_grade = session.scalar(
        select(PeriodGrade).where(
            PeriodGrade.academic_period_id == period.id,
            PeriodGrade.grade_id == grade.id,
        )
    )
    if period_grade is None:
        return
    offering = session.scalar(
        select(GradeSubjectOffering).where(
            GradeSubjectOffering.period_grade_id == period_grade.id,
            GradeSubjectOffering.subject_id == subject.id,
        )
    )
    if offering is None:
        return
    grade_enrollment = session.scalar(
        select(StudentGradeEnrollment).where(
            StudentGradeEnrollment.student_id == profile.id,
            StudentGradeEnrollment.academic_period_id == period.id,
            StudentGradeEnrollment.status == EnrollmentStatus.ACTIVE,
        )
    )
    if grade_enrollment is None:
        grade_enrollment = StudentGradeEnrollment(
            student_id=profile.id,
            academic_period_id=period.id,
            period_grade_id=period_grade.id,
            status=EnrollmentStatus.ACTIVE,
        )
        session.add(grade_enrollment)
        session.flush()
    if (
        session.scalar(
            select(StudentSubjectEnrollment).where(
                StudentSubjectEnrollment.student_id == profile.id,
                StudentSubjectEnrollment.grade_subject_offering_id == offering.id,
                StudentSubjectEnrollment.status == EnrollmentStatus.ACTIVE,
            )
        )
        is None
    ):
        session.add(
            StudentSubjectEnrollment(
                student_id=profile.id,
                grade_enrollment_id=grade_enrollment.id,
                grade_subject_offering_id=offering.id,
                status=EnrollmentStatus.ACTIVE,
            )
        )


def seed_approved_materials(
    session: Session,
    materials_dir: Path | None = None,
    *,
    replace: bool = False,
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

    if replace and _attempts_exist(session):
        raise RuntimeError("Cannot destructively replace seeded content after attempts exist")

    for sequence, topic_id in enumerate(topic_ids, start=1):
        _seed_subtopic(session, parent_topic, topic_id, sequence, directory)
    _seed_topic_mastery_quiz(session, parent_topic)
    seed_demo_student(session)

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
        seeded = seed_approved_materials(session, replace=False)
    engine.dispose()
    print(f"Seeded topics: {', '.join(seeded) if seeded else '(none)'}")


if __name__ == "__main__":
    main()

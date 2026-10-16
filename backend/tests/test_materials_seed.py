"""Unit tests for markdown curriculum parsing and seeding."""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from education_platform.modules.academics.constants import POC_TOPIC_SLUG
from education_platform.modules.academics.models import Subtopic, Topic
from education_platform.modules.assessments.models import QuestionAnswerKey
from education_platform.modules.materials.markdown_parser import (
    parse_objectives_from_lesson,
    parse_quiz,
)
from education_platform.modules.materials.seed import seed_approved_materials
from education_platform.modules.materials.seed_curriculum import ensure_curriculum_root

REPO_ROOT = Path(__file__).resolve().parents[2]
MATERIALS_DIR = REPO_ROOT / "docs" / "curriculum"


def test_parse_quiz_captures_answer_key() -> None:
    markdown = (MATERIALS_DIR / "square_numbers_patterns_quiz.md").read_text(encoding="utf-8")
    quiz = parse_quiz(markdown, "square_numbers_patterns")
    assert quiz.questions[0].correct_option_label == "B"
    assert quiz.questions[0].explanation is not None
    assert "1027" in (quiz.questions[0].explanation or "")


def test_parse_objectives_from_lesson_bullets() -> None:
    markdown = (MATERIALS_DIR / "square_numbers_patterns_lesson.md").read_text(encoding="utf-8")
    objectives = parse_objectives_from_lesson(markdown)
    assert len(objectives) >= 3
    assert any("square" in item.lower() for item in objectives)
    assert all("**" not in item for item in objectives)


def test_seed_stores_answer_keys_server_side(db_session: Session) -> None:
    seed_approved_materials(db_session, MATERIALS_DIR, replace=True)
    keys = db_session.scalars(select(QuestionAnswerKey)).all()
    assert len(keys) == 20


def test_seed_nests_curriculum_under_approved_materials(db_session: Session) -> None:
    parent = ensure_curriculum_root(db_session)
    db_session.add(
        Subtopic(
            topic_id=parent.id,
            name="Properties of Rectangles",
            slug="properties-of-rectangles",
            sequence=99,
        )
    )
    db_session.flush()

    seed_approved_materials(db_session, MATERIALS_DIR, replace=True)

    assert parent.slug == POC_TOPIC_SLUG
    assert parent.name == "Approved Materials"

    outline = db_session.scalar(select(Subtopic).where(Subtopic.slug == "properties-of-rectangles"))
    assert outline is not None
    assert outline.topic_id == parent.id
    assert db_session.scalar(select(Topic).where(Topic.slug == "properties-of-rectangles")) is None

    rectangles = db_session.scalar(
        select(Subtopic).where(Subtopic.slug == "rectangles_squares_properties")
    )
    assert rectangles is not None
    assert rectangles.topic_id == parent.id
    assert (
        db_session.scalar(select(Topic).where(Topic.slug == "rectangles_squares_properties"))
        is None
    )
    assert db_session.scalar(select(Topic).where(Topic.slug == "square_numbers_patterns")) is None


def test_seed_skips_approved_materials_bucket_when_chapters_exist(db_session: Session) -> None:
    bucket = ensure_curriculum_root(db_session)
    assert bucket is not None
    db_session.add(
        Topic(
            grade_subject_offering_id=bucket.grade_subject_offering_id,
            name="Properties of Rectangles and Squares",
            slug="rectangles_squares_properties",
            sequence=2,
        )
    )
    db_session.flush()
    db_session.delete(bucket)
    db_session.flush()

    seed_approved_materials(db_session, MATERIALS_DIR, replace=False)
    assert db_session.scalar(select(Topic).where(Topic.slug == POC_TOPIC_SLUG)) is None

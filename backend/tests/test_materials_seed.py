"""Unit tests for markdown curriculum parsing and seeding."""

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from education_platform.modules.assessments.models import QuestionAnswerKey
from education_platform.modules.materials.markdown_parser import (
    parse_objectives_from_lesson,
    parse_quiz,
)
from education_platform.modules.materials.seed import seed_approved_materials

REPO_ROOT = Path(__file__).resolve().parents[2]
MATERIALS_DIR = REPO_ROOT / "docs" / "materials"


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
    count = db_session.scalar(select(func.count()).select_from(QuestionAnswerKey))
    assert count == 20

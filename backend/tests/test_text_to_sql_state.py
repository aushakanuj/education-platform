"""Unit tests for the state["error"] category convention in state.py."""

from __future__ import annotations

import pytest

from education_platform.modules.text_to_sql.state import (
    LLM_ERROR,
    ROLE_VIOLATION,
    VALIDATION_ERROR,
    error_category,
    format_error,
)


@pytest.mark.parametrize("category", [LLM_ERROR, VALIDATION_ERROR, ROLE_VIOLATION])
def test_format_and_parse_round_trip(category: str) -> None:
    formatted = format_error(category, "some detail")
    assert formatted == f"{category}: some detail"
    assert error_category(formatted) == category


def test_format_error_rejects_unknown_category() -> None:
    with pytest.raises(ValueError, match="unknown error category"):
        format_error("SOMETHING_ELSE", "detail")


def test_error_category_returns_none_for_none() -> None:
    assert error_category(None) is None


def test_error_category_returns_none_for_foreign_text() -> None:
    # Text that never went through format_error (legacy, or a bug in some node) should
    # not be misclassified as one of the three known categories.
    assert error_category("some random exception message") is None
    assert error_category("validate_sql: old-style unprefixed message") is None


def test_the_three_categories_are_distinct() -> None:
    assert len({LLM_ERROR, VALIDATION_ERROR, ROLE_VIOLATION}) == 3

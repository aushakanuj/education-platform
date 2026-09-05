"""Focused tests for the YAML-backed Text-to-SQL intent router."""

from __future__ import annotations

import importlib
from typing import Any
from unittest.mock import AsyncMock

import pytest

from education_platform.core.config import Settings
from education_platform.modules.text_to_sql.graph import build_text_to_sql_graph
from education_platform.modules.text_to_sql.state import TextToSQLState

_MODULE = importlib.import_module(
    "education_platform.modules.text_to_sql.nodes.intent_router"
)


def _state() -> TextToSQLState:
    return {
        "question": "How many students do I teach?",
        "user_id": "user-1",
        "user_role": "teacher",
        "institution_id": "institution-1",
        "schema_context": "",
        "generated_sql": None,
        "validated_sql": None,
        "retry_count": 0,
        "error": None,
    }


def _mock_classifier(monkeypatch: pytest.MonkeyPatch, response: dict[str, Any]) -> None:
    monkeypatch.setattr(_MODULE, "get_settings", lambda: Settings(openrouter_api_key="test"))
    monkeypatch.setattr(
        _MODULE,
        "chat_completion_json",
        AsyncMock(return_value=response),
    )


@pytest.mark.asyncio
async def test_high_confidence_template_match(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_classifier(
        monkeypatch,
        {
            "intent": "count_my_students",
            "confidence": 0.96,
            "parameters": {},
            "operation": "count",
        },
    )

    result = await _MODULE.intent_router(_state())

    assert result["intent_route"] == "template"
    assert result["intent"] == "count_my_students"
    assert result["query_source"] == "template"
    assert result["generated_sql"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("subject", "canonical"),
    [
        ("Math", "Mathematics"),
        ("Maths", "Mathematics"),
        ("Mathematics", "Mathematics"),
        ("Sci", "Science"),
        ("Science", "Science"),
        ("Eng", "English"),
        ("Phy", "Physics"),
    ],
)
async def test_latest_quiz_attempt_subject_alias_is_normalized(
    monkeypatch: pytest.MonkeyPatch,
    subject: str,
    canonical: str,
) -> None:
    _mock_classifier(
        monkeypatch,
        {
            "intent": "latest_quiz_attempt",
            "confidence": 0.95,
            "parameters": {"subject": subject},
            "operation": "last",
        },
    )

    result = await _MODULE.intent_router(_state())

    assert result["intent_route"] == "template"
    assert result["intent"] == "latest_quiz_attempt"
    assert result["intent_parameters"] == {"subject": canonical}
    assert ":subject" in (result["generated_sql"] or "")


@pytest.mark.asyncio
async def test_latest_quiz_attempt_without_subject_uses_null_parameter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_classifier(
        monkeypatch,
        {
            "intent": "latest_quiz_attempt",
            "confidence": 0.95,
            "parameters": {},
            "operation": "latest",
        },
    )

    result = await _MODULE.intent_router(_state())

    assert result["intent_route"] == "template"
    assert result["intent"] == "latest_quiz_attempt"
    assert result["intent_parameters"] == {"subject": None}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        {"intent": "count_my_students", "confidence": 0.89, "parameters": {}, "operation": "count"},
        {"intent": "list_students_below_score_in_subject", "confidence": 0.95, "parameters": {"subject": "Mathematics"}, "operation": "list"},
        {"intent": "list_students_in_section", "confidence": 0.95, "parameters": {"section_name": "8A"}, "operation": "count"},
        {"intent": "count_my_students", "confidence": 0.95, "parameters": {}, "operation": "list", "ambiguous": True},
        {"intent": "students_meeting_performance_bar", "confidence": 0.99, "parameters": {}, "operation": "count"},
        {"intent": "unknown_intent", "confidence": 0.99, "parameters": {}, "operation": "count"},
    ],
)
async def test_invalid_or_ambiguous_decisions_fall_back_to_free_form(
    monkeypatch: pytest.MonkeyPatch,
    response: dict[str, Any],
) -> None:
    _mock_classifier(monkeypatch, response)

    result = await _MODULE.intent_router(_state())

    assert result["intent_route"] == "free_form"
    assert result.get("query_source") is None
    assert result.get("generated_sql") is None


@pytest.mark.asyncio
async def test_free_form_question_preserves_existing_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_classifier(
        monkeypatch,
        {"intent": None, "confidence": 0.73, "parameters": {}, "operation": None},
    )

    result = await _MODULE.intent_router(_state())

    assert result["intent_route"] == "free_form"
    assert result["query_source"] is None


def test_graph_places_router_after_question_validator() -> None:
    graph = build_text_to_sql_graph().get_graph()
    edges = {(edge.source, edge.target) for edge in graph.edges}

    assert ("question_validator", "intent_router") in edges
    assert ("intent_router", "validate_sql") in edges
    assert ("intent_router", "load_schema") in edges
    assert ("validate_sql", "generate_sql") in edges
    assert ("validate_sql", "apply_role_scope") in edges

"""Unit tests for the text-to-SQL question_validator node.

No database or network needed — chat_completion_json is monkeypatched throughout except
for the one test that deliberately exercises the real "OpenRouter not configured" path.
"""

from __future__ import annotations

import sys
from typing import Protocol, cast

import pytest

from education_platform.core.config import Settings
from education_platform.modules.assistant.openrouter import OpenRouterError
from education_platform.modules.text_to_sql.nodes.question_validator import question_validator
from education_platform.modules.text_to_sql.state import (
    OFF_TOPIC_REJECTED,
    TextToSQLState,
    error_category,
)


class _QuestionValidatorModule(Protocol):
    async def chat_completion_json(
        self, messages: list[dict[str, str]], *, settings: Settings, temperature: float = 0.0
    ) -> dict[str, object]: ...

    def get_settings(self) -> Settings: ...


# Same sys.modules reach-around injection_guard.py's own test file uses -- nodes/__init__.py
# rebinds the `nodes.question_validator` *attribute* to the function itself, so
# monkeypatching module-level names has to go through the real submodule.
_MODULE = cast(
    _QuestionValidatorModule,
    sys.modules["education_platform.modules.text_to_sql.nodes.question_validator"],
)


def _state(question: str, **overrides: object) -> TextToSQLState:
    state: TextToSQLState = {
        "question": question,
        "user_id": "u1",
        "user_role": "teacher",
        "institution_id": "i1",
        "error": None,
        "retry_count": 0,
        "audit_entry": None,
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


def _fake_classifier(response: dict[str, object]) -> object:
    calls: list[list[dict[str, str]]] = []

    async def _fake(
        messages: list[dict[str, str]], *, settings: Settings, temperature: float = 0.0
    ) -> dict[str, object]:
        calls.append(messages)
        return response

    return _fake, calls


# --- Off-topic questions get rejected ---------------------------------------------------


async def test_classifier_flags_an_off_topic_question(monkeypatch: pytest.MonkeyPatch) -> None:
    fake, _ = _fake_classifier({"off_topic": True, "reason": "asks about the weather"})
    monkeypatch.setattr(_MODULE, "chat_completion_json", fake)

    result = await question_validator(_state("What's the weather like tomorrow?"))

    assert error_category(result["error"]) == OFF_TOPIC_REJECTED


# --- Ordinary in-domain questions pass through unchanged, even when blunt/direct --------


@pytest.mark.parametrize(
    "question",
    [
        "How many students do I teach in total?",
        "Show me everyone in my class.",
        "I need to see all sections.",
        "What subject do I teach?",
    ],
)
async def test_in_domain_question_passes_through_unchanged(
    monkeypatch: pytest.MonkeyPatch, question: str
) -> None:
    fake, calls = _fake_classifier({"off_topic": False, "reason": ""})
    monkeypatch.setattr(_MODULE, "chat_completion_json", fake)

    state = _state(question)
    result = await question_validator(state)

    assert result["error"] is None
    assert result["question"] == state["question"]
    assert result["user_id"] == state["user_id"]
    assert len(calls) == 1


async def test_classifier_receives_only_the_current_question_no_identity_leaked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake, calls = _fake_classifier({"off_topic": False})
    monkeypatch.setattr(_MODULE, "chat_completion_json", fake)

    await question_validator(_state("What subjects do I teach?", user_id="secret-uuid-123"))

    sent_text = " ".join(m["content"] for m in calls[0])
    assert "secret-uuid-123" not in sent_text


# --- Fail-open when unconfigured, fail-closed when erroring -----------------------------


async def test_openrouter_not_configured_fails_open(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_MODULE, "get_settings", lambda: Settings(openrouter_api_key=None))

    async def _fail_if_called(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("classifier must not be called when OpenRouter isn't configured")

    monkeypatch.setattr(_MODULE, "chat_completion_json", _fail_if_called)

    result = await question_validator(_state("What's the weather like tomorrow?"))

    assert result["error"] is None


async def test_openrouter_error_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _raising(*args: object, **kwargs: object) -> dict[str, object]:
        raise OpenRouterError("network blew up")

    monkeypatch.setattr(_MODULE, "chat_completion_json", _raising)

    result = await question_validator(_state("How many students do I teach in total?"))

    assert error_category(result["error"]) == OFF_TOPIC_REJECTED


async def test_malformed_classifier_response_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    fake, _ = _fake_classifier({"not_the_expected_shape": True})
    monkeypatch.setattr(_MODULE, "chat_completion_json", fake)

    result = await question_validator(_state("How many students do I teach in total?"))

    # Pydantic requires `off_topic: bool` with no default -- a response missing it fails
    # validation, which this node treats the same as any other classifier failure: fail
    # closed, not crash and not silently pass through.
    assert error_category(result["error"]) == OFF_TOPIC_REJECTED

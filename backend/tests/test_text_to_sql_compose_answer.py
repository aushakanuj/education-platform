"""Unit tests for the text-to-SQL compose_answer node.

No database needed — chat_completion is monkeypatched throughout. The row-cap-truncation
test chained from a *real* execute_sql call lives in
test_text_to_sql_compose_answer_integration.py, which needs Postgres, matching the rigor
of Task 8's equivalent test.
"""

from __future__ import annotations

import sys
from typing import Protocol, cast

import pytest

from education_platform.core.config import Settings
from education_platform.modules.assistant.openrouter import OpenRouterError
from education_platform.modules.text_to_sql.nodes.compose_answer import (
    _CONFIDENCE_HEDGE,
    _TRUNCATION_DISCLOSURE,
    compose_answer,
)
from education_platform.modules.text_to_sql.state import TextToSQLState


class _ComposeAnswerModule(Protocol):
    """Typed view of compose_answer.py's module namespace, for patching chat_completion
    where compose_answer.py actually looks it up.
    """

    async def chat_completion(
        self, messages: list[dict[str, str]], *, settings: Settings, temperature: float = 0.0
    ) -> str: ...

    def get_settings(self) -> Settings: ...


# `nodes/__init__.py` does `from .compose_answer import compose_answer as compose_answer`,
# which rebinds the `nodes.compose_answer` *attribute* from the submodule to the function
# (same gotcha as generate_sql/execute_sql — see test_text_to_sql_generate_sql.py). Reach
# the real submodule via sys.modules to monkeypatch chat_completion.
_MODULE = cast(
    _ComposeAnswerModule,
    sys.modules["education_platform.modules.text_to_sql.nodes.compose_answer"],
)


def _base_state(**overrides: object) -> TextToSQLState:
    state: TextToSQLState = {
        "question": "how many students are enrolled?",
        "validated_sql": "SELECT COUNT(*) AS count FROM student_subject_enrollments",
        "query_result": [{"count": 42}],
        "result_row_count": 1,
        "confidence": "high",
        "audit_entry": None,
        "error": None,
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


def _fake_chat_completion(response: str) -> tuple[object, dict[str, object]]:
    captured: dict[str, object] = {}

    async def _fake(
        messages: list[dict[str, str]], *, settings: Settings, temperature: float = 0.0
    ) -> str:
        captured["messages"] = messages
        return response

    return _fake, captured


async def _never_called(*args: object, **kwargs: object) -> str:
    raise AssertionError("chat_completion should not have been called for this result shape")


def _answer(result: TextToSQLState) -> str:
    value = result["natural_answer"]
    assert value is not None
    return value


def _provenance_of(result: TextToSQLState) -> str:
    value = result["provenance"]
    assert value is not None
    return value


# --- LLM call vs. deterministic templating -----------------------------------------------


async def test_single_scalar_result_does_not_call_the_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_MODULE, "chat_completion", _never_called)

    result = await compose_answer(
        _base_state(query_result=[{"count": 42}], result_row_count=1)
    )

    assert _answer(result) == "The count is 42."


async def test_zero_row_result_does_not_call_the_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_MODULE, "chat_completion", _never_called)

    result = await compose_answer(_base_state(query_result=[], result_row_count=0))

    assert _answer(result) == "I couldn't find any records matching that question."


async def test_multi_row_result_calls_the_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    fake, captured = _fake_chat_completion("Both students are passing their classes.")
    monkeypatch.setattr(_MODULE, "chat_completion", fake)

    rows = [{"name": "A", "passed": True}, {"name": "B", "passed": True}]
    result = await compose_answer(
        _base_state(
            question="are my students passing?", query_result=rows, result_row_count=2
        )
    )

    assert _answer(result) == "Both students are passing their classes."
    messages = cast(list[dict[str, str]], captured["messages"])
    user_content = messages[-1]["content"]
    assert "are my students passing?" in user_content
    assert '"name": "A"' in user_content


async def test_single_row_multiple_columns_calls_the_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Row-count 1 but more than one column — not the single-scalar template shape.
    fake, _ = _fake_chat_completion("Aisha is in grade 8, section 8A.")
    monkeypatch.setattr(_MODULE, "chat_completion", fake)

    result = await compose_answer(
        _base_state(
            question="what grade and section is Aisha in?",
            query_result=[{"grade": "8", "section": "8A"}],
            result_row_count=1,
        )
    )
    assert _answer(result) == "Aisha is in grade 8, section 8A."


async def test_llm_failure_falls_back_to_a_generic_honest_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raising(
        messages: list[dict[str, str]], *, settings: Settings, temperature: float = 0.0
    ) -> str:
        raise OpenRouterError("connection reset")

    monkeypatch.setattr(_MODULE, "chat_completion", _raising)

    rows = [{"id": 1}, {"id": 2}, {"id": 3}]
    result = await compose_answer(_base_state(query_result=rows, result_row_count=3))

    assert _answer(result) == "Found 3 matching records."


# --- Confidence must show up in the words --------------------------------------------


async def test_high_confidence_answer_has_no_hedging_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_MODULE, "chat_completion", _never_called)

    result = await compose_answer(
        _base_state(query_result=[{"count": 42}], result_row_count=1, confidence="high")
    )

    answer = _answer(result)
    assert "preliminary" not in answer.lower()
    assert _CONFIDENCE_HEDGE not in answer


async def test_medium_confidence_answer_differs_demonstrably_from_high(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_MODULE, "chat_completion", _never_called)

    high = await compose_answer(
        _base_state(query_result=[{"count": 42}], result_row_count=1, confidence="high")
    )
    medium = await compose_answer(
        _base_state(query_result=[{"count": 42}], result_row_count=1, confidence="medium")
    )

    high_answer, medium_answer = _answer(high), _answer(medium)
    assert high_answer != medium_answer
    assert _CONFIDENCE_HEDGE in medium_answer
    assert _CONFIDENCE_HEDGE not in high_answer


async def test_low_confidence_answer_differs_demonstrably_from_high(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_MODULE, "chat_completion", _never_called)

    high = await compose_answer(
        _base_state(query_result=[{"count": 42}], result_row_count=1, confidence="high")
    )
    low = await compose_answer(
        _base_state(query_result=[{"count": 42}], result_row_count=1, confidence="low")
    )

    high_answer, low_answer = _answer(high), _answer(low)
    assert high_answer != low_answer
    assert _CONFIDENCE_HEDGE in low_answer


# --- Row-cap truncation: always a real sentence, isolated flag version -----------------


async def test_row_cap_truncated_flag_produces_the_disclosure_sentence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake, _ = _fake_chat_completion("Here are the matching records.")
    monkeypatch.setattr(_MODULE, "chat_completion", fake)

    rows = [{"id": i} for i in range(10)]
    result = await compose_answer(
        _base_state(
            query_result=rows,
            result_row_count=10,
            audit_entry={"row_cap_truncated": True},
        )
    )

    assert _TRUNCATION_DISCLOSURE in _answer(result)


async def test_row_cap_flag_absent_produces_no_disclosure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_MODULE, "chat_completion", _never_called)

    result = await compose_answer(
        _base_state(query_result=[{"count": 1}], result_row_count=1, audit_entry=None)
    )

    assert _TRUNCATION_DISCLOSURE not in _answer(result)


# --- Zero rows read as an honest, complete answer --------------------------------------


async def test_zero_row_result_reads_as_honest_not_a_broken_empty_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_MODULE, "chat_completion", _never_called)

    result = await compose_answer(
        _base_state(
            question="which students failed the quiz?",
            query_result=[],
            result_row_count=0,
            confidence="high",
        )
    )

    answer = _answer(result)
    assert answer  # not empty/falsy
    assert answer != "0"
    assert "None" not in answer
    assert answer == "I couldn't find any records matching that question."


# --- Single-scalar formatting details ---------------------------------------------------


async def test_single_scalar_percentage_column_formats_with_percent_sign(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_MODULE, "chat_completion", _never_called)

    result = await compose_answer(
        _base_state(query_result=[{"mastery_percent": 82.5}], result_row_count=1)
    )
    assert _answer(result) == "The mastery percent is 82.5%."


async def test_single_scalar_null_value_phrased_as_no_data_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_MODULE, "chat_completion", _never_called)

    result = await compose_answer(
        _base_state(query_result=[{"attendance_percent": None}], result_row_count=1)
    )
    assert _answer(result) == "No attendance percent data is available for that."


# --- provenance: describes what was queried, never raw SQL -----------------------------


async def test_provenance_lists_queried_tables() -> None:
    result = await compose_answer(
        _base_state(
            validated_sql="SELECT sp.id FROM student_profiles sp JOIN quiz_attempts qa "
            "ON qa.student_id = sp.id",
            query_result=[{"count": 1}],
            result_row_count=1,
        )
    )
    provenance = _provenance_of(result)
    assert "student_profiles" in provenance
    assert "quiz_attempts" in provenance


async def test_provenance_never_contains_raw_sql() -> None:
    result = await compose_answer(
        _base_state(
            validated_sql=(
                "SELECT id FROM student_profiles WHERE full_name = 'Unmistakable Secret Name'"
            ),
            query_result=[{"count": 1}],
            result_row_count=1,
        )
    )
    provenance = _provenance_of(result)
    assert "Unmistakable Secret Name" not in provenance
    assert "SELECT" not in provenance
    assert "WHERE" not in provenance
    assert "student_profiles" in provenance  # the table name is fine, the query text isn't


async def test_provenance_mechanism_cannot_leak_sql_keywords_embedded_in_literal_values() -> None:
    # Table-name extraction walks the sqlglot AST for exp.Table nodes only -- it never
    # does string search/redaction over the SQL text -- so a literal *value* that happens
    # to contain a SQL-keyword-shaped substring can't leak through structurally, not just
    # "didn't happen to trigger in this particular test's data" the way the test above
    # only proves for one specific literal. A naive text-based redaction approach could
    # plausibly miss "Selecta" (contains "Select") or fail on "DROP-001-WHERE"; parsing
    # to an AST and reading only .name off exp.Table nodes never even looks at literals.
    result = await compose_answer(
        _base_state(
            validated_sql=(
                "SELECT id FROM student_profiles WHERE full_name = 'Selecta Smith' "
                "AND student_identifier = 'DROP-001-WHERE'"
            ),
            query_result=[{"count": 1}],
            result_row_count=1,
        )
    )
    provenance = _provenance_of(result)
    assert "Selecta Smith" not in provenance
    assert "DROP-001-WHERE" not in provenance
    assert "student_profiles" in provenance


async def test_provenance_includes_sanity_check_triggers_when_present() -> None:
    result = await compose_answer(
        _base_state(
            query_result=[],
            result_row_count=0,
            confidence="medium",
            audit_entry={"sanity_check_triggers": ["zero_rows: query returned no rows"]},
        )
    )
    assert "zero_rows" in _provenance_of(result)


async def test_provenance_has_no_triggers_line_when_clean() -> None:
    result = await compose_answer(
        _base_state(query_result=[{"count": 1}], result_row_count=1, audit_entry=None)
    )
    assert "flagged" not in _provenance_of(result).lower()


# --- state["error"] already set: never fabricate an answer over it ---------------------


async def test_preexisting_error_is_never_overwritten_with_a_fabricated_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_MODULE, "chat_completion", _never_called)

    state = _base_state(
        error="EXECUTION_ERROR: the query could not be run",
        query_result=None,
        result_row_count=None,
    )
    result = await compose_answer(state)

    assert result == state
    assert result.get("natural_answer") is None
    assert result["error"] == "EXECUTION_ERROR: the query could not be run"

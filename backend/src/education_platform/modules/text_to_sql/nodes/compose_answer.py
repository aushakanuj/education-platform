"""Turns state["query_result"] into state["natural_answer"] and state["provenance"].
Honors everything upstream nodes already decided — never re-derives or second-guesses
state["confidence"], state["error"], or the data itself. This node phrases; it does not
judge.

**LLM call: only when the data actually needs natural-language shaping.** Two result
shapes are fully deterministic and get templated phrasing with no model call at all:

* **Zero rows** — "I couldn't find any records matching that question." is the honest,
  complete answer; there is nothing for a model to add.
* **A single row with a single column** — the classic COUNT/AVG/aggregate shape (e.g.
  `{"mastery_percent": 82.5}`). The value is rendered directly from the row, verbatim,
  with a light templated sentence built from the column name — never re-typed or
  paraphrased by a model, which is one less place a number that is already correct could
  come out wrong. (This is a *different* case from zero rows: `SELECT COUNT(*) ...`
  always returns exactly one row, even when the count is 0 — that row still goes through
  this path, not the zero-row one.)

Everything else — a multi-row result, or a single row with more than one column — goes
through an LLM call (same OpenRouter client/pattern as generate_sql) to turn the rows into
readable prose, since summarizing or describing a list well is exactly the kind of task
templating handles badly and language models handle well. The prompt instructs the model
to use only the values it's given and never invent, estimate, or alter any of them; if the
call itself fails (network/API error), this falls back to a generic-but-honest templated
count rather than surfacing a pipeline error over what is otherwise a fully successful
query — the LLM only shapes phrasing here, it was never the thing that could make the
answer wrong.

**Confidence must show up in the words, not just ride along as a field.** Any
`state["confidence"]` other than `"high"` gets a fixed, always-appended hedge sentence
(`_CONFIDENCE_HEDGE`) — appended deterministically after whatever core answer was
produced, never left to the model to remember to include. This guarantees, by
construction, that a medium/low-confidence answer can never read identically to a
high-confidence one: the hedge sentence is either present or it isn't, nothing in between.

**Row-cap truncation is the same pattern.** If `state["audit_entry"]["row_cap_truncated"]`
is set (Task 7 truncated the result), a fixed disclosure sentence naming the actual cap
(`execute_sql.ROW_CAP`, imported, not a second literal) is appended the same
deterministic way — never dependent on the model choosing to mention it.

**provenance** describes what was queried and, if any, which confidence-affecting checks
fired — enough for a teacher or admin to sanity-check where a number came from — but never
the raw SQL text itself (this pipeline's own rule: SQL is never user-facing, only logged
via audit_log). Table names are recovered by parsing `state["validated_sql"]` with
sqlglot (the same tool this pipeline already uses everywhere else for structural SQL
work) and keeping only the table *names* found, discarding the query text itself — the
parse is a display convenience here, not a security boundary, so it doesn't need
apply_role_scope's CTE-alias rigor.

**state["error"] already set:** under graph.py's current wiring this is structurally
unreachable — compose_answer's only incoming edges come from sanity_check, which itself
only runs after execute_sql's "ok" edge (i.e. no error). But this node checks anyway and
returns state completely untouched if an error is already present, rather than trusting
that invariant to hold forever: a future routing change is exactly the kind of thing that
could quietly violate it, and fabricating a confident-sounding answer over a real error
would be a worse failure mode than a defensive check that should never fire.
"""

from __future__ import annotations

import json
from typing import Any, Final

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from education_platform.core.config import get_settings
from education_platform.modules.assistant.openrouter import OpenRouterError, chat_completion
from education_platform.modules.text_to_sql.nodes.execute_sql import ROW_CAP
from education_platform.modules.text_to_sql.nodes.sanity_check import PERCENTAGE_COLUMNS
from education_platform.modules.text_to_sql.state import TextToSQLState

_ZERO_ROW_ANSWER: Final[str] = "I couldn't find any records matching that question."

_CONFIDENCE_HEDGE: Final[str] = (
    "This is a preliminary estimate — a data-quality check flagged this result, so please "
    "treat it as approximate rather than final (see the audit trail for specifics)."
)

_TRUNCATION_DISCLOSURE: Final[str] = (
    f"This shows only the first {ROW_CAP} results — narrow your question for a complete count."
)

_MAX_ROWS_IN_PROMPT: Final[int] = 50

_SYSTEM_PROMPT = """You answer questions about school data using ONLY the query result \
rows you are given.

Rules:
- Use ONLY the values in the provided rows. Never invent, estimate, round differently, \
or alter any number, name, or fact that isn't literally present in the data.
- Write 1-4 sentences of plain, natural language a teacher or administrator would find \
clear and easy to read.
- Prefer plain-English phrasing over raw field names where it reads naturally (e.g. \
"attendance rate" rather than "attendance_percent"), but never change the underlying \
value while doing so.
- Do not mention SQL, tables, columns, queries, or any other database internals.
- Do not add any caveats about confidence, completeness, or data quality — that is \
handled separately, outside your answer.
- Answer only the question asked; do not add unrelated commentary."""


def _humanize_column(name: str) -> str:
    return name.replace("_", " ").strip()


def _single_scalar_answer(column: str, value: Any) -> str:
    label = _humanize_column(column)
    if value is None:
        return f"No {label} data is available for that."
    if column.lower() in PERCENTAGE_COLUMNS:
        return f"The {label} is {value}%."
    return f"The {label} is {value}."


def _serialize_rows_for_prompt(rows: list[dict[str, Any]]) -> str:
    shown = rows[:_MAX_ROWS_IN_PROMPT]
    lines = [json.dumps(row, default=str) for row in shown]
    body = "\n".join(lines)
    if len(rows) > _MAX_ROWS_IN_PROMPT:
        body += f"\n... and {len(rows) - _MAX_ROWS_IN_PROMPT} more row(s) not shown here."
    return body


def _build_messages(question: str, rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    user_content = (
        f"Question: {question}\n\n"
        f"Query result rows ({len(rows)} total):\n{_serialize_rows_for_prompt(rows)}"
    )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _fallback_summary(rows: list[dict[str, Any]]) -> str:
    count = len(rows)
    noun = "record" if count == 1 else "records"
    return f"Found {count} matching {noun}."


async def _llm_answer(question: str, rows: list[dict[str, Any]]) -> str:
    settings = get_settings()
    messages = _build_messages(question, rows)
    try:
        raw = await chat_completion(messages, settings=settings, temperature=0.0)
    except OpenRouterError:
        return _fallback_summary(rows)
    text = raw.strip()
    return text if text else _fallback_summary(rows)


async def _compose_core_answer(
    question: str, rows: list[dict[str, Any]], row_count: int
) -> str:
    if row_count == 0:
        return _ZERO_ROW_ANSWER
    if row_count == 1 and len(rows[0]) == 1:
        ((column, value),) = rows[0].items()
        return _single_scalar_answer(column, value)
    return await _llm_answer(question, rows)


def _tables_referenced(sql: str | None) -> list[str]:
    if not sql:
        return []
    try:
        tree = sqlglot.parse_one(sql, read="postgres")
    except SqlglotError:
        return []
    return sorted({table.name.lower() for table in tree.find_all(exp.Table)})


def _provenance(state: TextToSQLState) -> str:
    tables = _tables_referenced(state.get("validated_sql"))
    parts = [f"Queried: {', '.join(tables)}." if tables else "No tables were queried."]
    audit_entry = state.get("audit_entry") or {}
    triggers = audit_entry.get("sanity_check_triggers") or []
    if triggers:
        parts.append("Data-quality checks flagged: " + "; ".join(triggers) + ".")
    return " ".join(parts)


async def compose_answer(state: TextToSQLState) -> TextToSQLState:
    if state.get("error"):
        return state

    rows = state.get("query_result") or []
    row_count = state.get("result_row_count")
    if row_count is None:
        row_count = len(rows)
    question = state.get("question") or ""
    confidence = state.get("confidence") or "high"
    audit_entry = state.get("audit_entry") or {}

    sentences = [await _compose_core_answer(question, rows, row_count)]
    if confidence != "high":
        sentences.append(_CONFIDENCE_HEDGE)
    if audit_entry.get("row_cap_truncated"):
        sentences.append(_TRUNCATION_DISCLOSURE)

    return {
        **state,
        "natural_answer": " ".join(sentences),
        "provenance": _provenance(state),
    }

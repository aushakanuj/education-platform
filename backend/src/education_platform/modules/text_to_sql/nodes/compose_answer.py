"""Turns state["query_result"] into state["natural_answer"] and state["provenance"].
Honors everything upstream nodes already decided — never re-derives or second-guesses
state["confidence"], state["error"], or the data itself. This node phrases; it does not
judge.

**LLM call: only when the data actually needs natural-language shaping.** Three result
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
* **A small, single-column list** (2 to `_ENUMERABLE_LIST_ROW_CAP` rows, every row
  carrying just one column of the same name — e.g. "what subjects do I teach" returning
  `[{"name": "Mathematics"}, {"name": "Science"}]`). This is the same shape as the
  single-scalar case, generalized along one dimension (several values instead of one),
  and it carries the exact same risk the single-scalar case was built to avoid: real
  evidence (a live eval run) showed the LLM-summarization path silently dropping one of
  three real values when asked "what subject do I teach" — a teacher with Mathematics and
  Science assignments got told "You teach Mathematics," Science omitted, no error, no low
  confidence, nothing to signal the answer was incomplete. That's exactly the "a number
  that is already correct could come out wrong" failure Task 9 built the single-scalar
  path to prevent, just for a short list instead of one value — so the same fix applies:
  enumerate the distinct values directly from the rows (deduplicated, order preserved),
  never re-typed by a model. The cap (10) is a readability judgment, not a correctness
  one: enumerating "Mathematics, Science, and English" reads fine; enumerating 30 rows
  does not, and at that size a real prose summary is more useful anyway — see the LLM
  path below for anything past the cap, and for any multi-column result at any size,
  where a safe generic template does not exist.

  **Scope, deliberately narrow — attribute lists, never entity rosters.** This path
  fires only when the shared column is literally named `name` (`_single_column_list_shape`
  gates on the exact string, not just "one column"), never on `full_name` or anything
  else. That's not an arbitrary restriction: deduplicating is only safe for a small,
  closed *attribute/category* set (a subject, a section, a grade — "teaches Mathematics"
  is one true fact no matter how many rows say so) and actively unsafe for an *entity
  roster* (student names, or any list meant to enumerate distinct people/things), where a
  repeated-looking value could be a genuine duplicate-row bug or two different real
  entities sharing a label — either way, silently merging them would hide something worth
  seeing rather than fix a display quirk. The schema already draws this line on its own:
  every person-identifying table (`users`, `student_profiles`) names this column
  `full_name`; every attribute table this pipeline exposes names it bare `name`. A future
  change that widens this path to more columns must re-justify that the new column is
  genuinely attribute-shaped, not assume the cap/shape checks alone are sufficient — they
  were never the safety mechanism here, the column name is.

Everything else — a multi-row result with more than one column, a single-column list
past the enumeration cap, or a single-column list whose column isn't `name` (a student
roster, a bare list of scores, ...) — goes through an LLM call (same OpenRouter
client/pattern as generate_sql) to turn the rows into readable prose, since summarizing or
describing a larger, richer, or entity-identifying result well is exactly the kind of task
templating handles badly (or unsafely) and language models handle well. The prompt
instructs the model to use only the values it's
given and never invent, estimate, or alter any of them; if the call itself fails
(network/API error), this falls back to a generic-but-honest templated count rather than
surfacing a pipeline error over what is otherwise a fully successful query — the LLM only
shapes phrasing here, it was never the thing that could make the answer wrong. It can,
however, as the single-column-list finding above shows, make the answer *incomplete*
without any signal that it did — a real, open risk for every result shape still on this
path (multi-column, or single-column past the cap), not just the one case just fixed.

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

# See the module docstring's third deterministic-templating bullet: a small, single-column
# list is enumerated directly rather than trusted to an LLM summarization call. Chosen so
# the enumerated sentence stays readable ("Mathematics, Science, and English") rather than
# becoming an unreadable wall of comma-separated items -- past this size a real prose
# summary from the LLM path is more useful than a flat list anyway.
_ENUMERABLE_LIST_ROW_CAP: Final[int] = 10

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


def _english_join(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _single_column_list_shape(rows: list[dict[str, Any]], row_count: int) -> str | None:
    """The shared column name if every row in `rows` has exactly one column, all sharing
    that same name, that name is the schema's own attribute-label convention (see below),
    and the list is short enough to enumerate directly (see `_ENUMERABLE_LIST_ROW_CAP`) —
    `None` if this isn't that shape at all. `row_count` is the caller's own already-
    computed count (`state["result_row_count"]`, falling back to `len(rows)`), not
    re-derived from `len(rows)` here, so a truncated `query_result` list can't be mistaken
    for a genuinely short result.

    Scope boundary, deliberate and load-bearing — do not widen without re-reading this:
    this path deduplicates (see `_enumerated_list_answer`), which is only safe for a
    small, closed *attribute/category* set (a subject name, a section name, a grade name)
    where two rows carrying the same value are, semantically, the same real-world fact
    stated twice — "teaches Mathematics" is true once no matter how many of a teacher's
    rows say so. It is NOT safe for an *entity roster* (student names, or any list where
    each row is meant to represent a distinct person or thing): two rows with the same
    name there could be a genuine duplicate-row bug (undetected by this node, which never
    re-derives correctness — see the module docstring) or, just as plausibly, two
    different real students who happen to share a name — either way, silently merging
    them into one listed entry would hide something worth seeing, not fix a display quirk.
    The schema's own naming convention already draws this line for us: every person-
    identifying table (`users`, `student_profiles`) names this column `full_name`;
    every attribute/category table this pipeline exposes (`subjects`, `grades`,
    `sections`, and their peers) names it bare `name`. Gating on the literal column name
    `"name"` — not just "single column, short list" — is what keeps this path out of
    roster territory without needing to know what table the model actually queried.
    """
    if not (1 < row_count <= _ENUMERABLE_LIST_ROW_CAP) or len(rows) != row_count:
        return None
    columns = {frozenset(row.keys()) for row in rows}
    if len(columns) != 1:
        return None
    (only_columns,) = columns
    if len(only_columns) != 1:
        return None
    (column,) = only_columns
    if column != "name":
        return None
    return column


def _enumerated_list_answer(column: str, rows: list[dict[str, Any]]) -> str:
    # `column` is always literally "name" here — see `_single_column_list_shape`'s gate —
    # never one of PERCENTAGE_COLUMNS, so no percent-sign formatting applies (a bare list
    # of percentage values would carry the same "two rows, same value, is that one real
    # fact or two coincidentally-equal ones?" ambiguity as an entity roster, which is
    # exactly what that gate exists to keep out of this deterministic path).
    label = "Name"  # sentence-initial here, unlike the single-scalar template's
    # "The {label} is ..." mid-sentence placement.
    seen: dict[str, None] = {}  # dict, not set: preserves first-seen order: deduplicated,
    # never re-typed by a model, directly from the real rows. Deduplication is safe only
    # because `column == "name"` restricts this to attribute/category labels (subjects,
    # sections, grades) — see the scope-boundary note on `_single_column_list_shape`.
    for row in rows:
        seen.setdefault(str(row[column]), None)
    return f"{label}: {_english_join(list(seen))}."


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
    list_column = _single_column_list_shape(rows, row_count)
    if list_column is not None:
        return _enumerated_list_answer(list_column, rows)
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

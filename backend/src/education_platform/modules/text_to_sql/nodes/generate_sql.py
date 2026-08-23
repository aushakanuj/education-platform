"""Calls an LLM (via OpenRouter, same client as `assistant`) to turn state["question"]
into a single SQL SELECT statement, using only what's in state["schema_context"].

Retry handling: this node owns state["retry_count"]. If it's entered with
state["error"] already set — meaning it was reached via the validate_sql -> invalid ->
generate_sql edge, not the graph's entry point — it increments retry_count as the very
first thing it does, before calling the LLM, and folds the previous attempt's SQL and
rejection reason into the prompt so the model has a real correction signal instead of
regenerating blind. The retry-count *ceiling* (routing to honest_refusal once
MAX_RETRIES is hit) stays graph.py's job, per Task 2 — this node only increments.

LLM-call failures (network/API errors, missing OPENROUTER_API_KEY) are a different
failure class from a SQL validation rejection: they mean no SQL was produced at all,
not that produced SQL was rejected. They're tagged `state.py`'s shared `LLM_ERROR`
category (via `format_error()`) so they stay legible as a different kind of problem
wherever `state["error"]` ends up being read (logs, audit_log, a future validate_sql) —
see `state.py` for the full category convention every error-producing node uses.

Note this only makes the two classes distinguishable by *content* — it does not change
how many retries an LLM outage burns through the graph's retry loop. retry_count still
increments on any pre-existing error per Task 2/4's spec (unconditional on error
class), so if an LLM failure loops back around through validate_sql and returns here
again, that re-entry still consumes one of the 3 retries, same as a validation
rejection would. Exempting LLM failures from the retry budget would need a
graph.py/validate_sql.py change (a separate signal the routing checks), which is out
of this node's scope.
"""

from __future__ import annotations

import re

from education_platform.core.config import get_settings
from education_platform.modules.assistant.openrouter import OpenRouterError, chat_completion
from education_platform.modules.text_to_sql.state import LLM_ERROR, TextToSQLState, format_error

_SYSTEM_PROMPT = """You are a SQL generation assistant for an education platform's \
PostgreSQL database.

Given a natural-language question, a schema catalog describing the available tables \
and columns, and the asking user's role, write exactly one read-only SQL query that \
answers the question.

Rules:
- Use ONLY tables and columns that appear in the schema catalog. Never invent a table \
or column name, and never guess at one that isn't shown.
- Write exactly one SELECT statement. Never write INSERT, UPDATE, DELETE, DROP, \
ALTER, TRUNCATE, GRANT, or any other statement type.
- Do not add a trailing semicolon.
- The user's role is given so you can correctly interpret role-relative language in \
the question (e.g. "my students", "my score") — write the query naturally for what \
the question asks. Row-level access enforcement for that role is applied in a \
separate step after your query is generated; you do not need to hand-roll \
access-control filtering yourself, but do not drop a WHERE clause the question itself \
asks for.
- Return ONLY the SQL query, in a single ```sql fenced code block, with no other \
commentary before or after it."""

_FENCE_RE = re.compile(r"```(?:sql)?\s*\n?(.*?)```", re.DOTALL | re.IGNORECASE)


def _build_messages(
    *,
    question: str,
    schema_context: str,
    user_role: str,
    prior_sql: str | None,
    prior_error: str | None,
) -> list[dict[str, str]]:
    user_content = (
        f"Schema:\n{schema_context}\n\nAsking user's role: {user_role}\n\nQuestion: {question}"
    )
    if prior_sql or prior_error:
        user_content += (
            "\n\nYour previous attempt was rejected. Fix the specific problem below "
            "rather than starting over from scratch.\n\n"
            f"Previous SQL:\n{prior_sql or '(none produced)'}\n\n"
            f"Rejection reason:\n{prior_error or '(not given)'}"
        )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _extract_sql(raw: str) -> str:
    match = _FENCE_RE.search(raw)
    candidate = match.group(1) if match else raw
    return candidate.strip().rstrip(";").strip()


async def generate_sql(state: TextToSQLState) -> TextToSQLState:
    incoming_error = state.get("error")
    retry_count = state.get("retry_count", 0)
    is_retry = bool(incoming_error)
    if is_retry:
        retry_count += 1

    messages = _build_messages(
        question=state["question"],
        schema_context=state.get("schema_context") or "",
        user_role=state.get("user_role") or "unknown",
        prior_sql=state.get("generated_sql") if is_retry else None,
        prior_error=incoming_error if is_retry else None,
    )

    settings = get_settings()
    try:
        raw = await chat_completion(messages, settings=settings, temperature=0.0)
    except OpenRouterError as exc:
        return {
            **state,
            "retry_count": retry_count,
            "error": format_error(LLM_ERROR, f"generate_sql: OpenRouter call failed: {exc}"),
        }

    sql = _extract_sql(raw)
    if not sql:
        return {
            **state,
            "retry_count": retry_count,
            "error": format_error(LLM_ERROR, "generate_sql: model returned an empty query"),
        }

    return {
        **state,
        "retry_count": retry_count,
        "generated_sql": sql,
        "error": None,
    }

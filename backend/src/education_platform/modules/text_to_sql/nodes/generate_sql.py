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

Self-reference sentinel (`'__CURRENT_USER_ID__'`): for the tables apply_role_scope
scopes down to *exactly* the asking user's own rows (student_360, quiz_attempts, etc.),
the model never needs to write a self-filter at all — apply_role_scope adds it silently.
But for a table it only institution-pins (teaching_assignments, users, ...), a question
like "what subject do I teach" genuinely needs a `teacher_user_id = <me>` filter that
only the model can write, and this node never gives the model any real identity value to
use (no user_id, no name, no email — by design, matching the rest of this pipeline's
identity-sourcing discipline). Observed failure mode without this: the model fabricates
a placeholder literal (e.g. `'Your Name Here'`) that matches nothing, producing a
confidently-wrong empty answer for a real, answerable question. The system prompt below
teaches one fixed, literal token instead (never a name/guess/subquery); apply_role_scope
resolves it to the real `state["user_id"]` before execution — the same node, and the
same "identity only ever comes from state, never from the model" discipline, that
already builds every other identity-keyed predicate in this pipeline.

Multi-row-per-entity joins (DISTINCT/EXISTS guidance): a live eval run found "list the
students enrolled in my subject offerings" returning 120 rows for a teacher with 72 real
students. Root cause, confirmed against real data: the query joined `teaching_assignments`
directly, and this teacher (like every teacher in the seed data checked — 24 of 24 have
this shape) has two assignment rows for the same subject offering, one per section she
teaches. Every matching student got counted once per matching assignment row. This isn't
`apply_role_scope`'s bug — its own injected predicates already use `EXISTS(...)`
specifically to avoid this — it's that the model's own join, written for filtering rather
than for reading an assignment-specific column, multiplies rows the same way any
un-deduplicated JOIN would. `quiz_attempts` has the identical shape for a different
reason (`attempt_number`). The system prompt below teaches the general pattern —
`DISTINCT` or `EXISTS` — rather than special-casing either table, since this is a
structural property of the schema (any table modeling a one-to-many relationship the
question doesn't care about the "many" side of), not a one-off.

Avoid unnecessary deferred-table routing: the same eval run found 3 of 39 questions
(rows asking about a specific quiz's pass rate, a subject-filtered score list, and
unsubmitted quiz attempts) routed through `quiz_versions`/`topics` and got refused by
`apply_role_scope`'s Roadmap-7A deferred-table gate — even though structurally similar
questions elsewhere in the same run answered successfully via a simpler path (`subjects`
directly, or `quiz_attempts` alone). A real, recurring pattern (not a one-off), not a
security concern (the refusal is safe), but an avoidable one: the system prompt below
asks the model to prefer the simplest join path and reserve the curriculum tables for
when the question genuinely can't be answered without them.
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
- If the question needs to compare a column against the identity of the person asking \
(e.g. "what subject do I teach" needs teacher_user_id = <the asking teacher>, "what's \
my email" needs id = <the asking user>), you do not know that person's real ID, name, \
or email — never invent, guess, or leave blank a value for this. Instead write the \
exact literal string '__CURRENT_USER_ID__' (including the quotes and underscores) as \
the comparison value; a separate step after generation resolves it to the asking \
user's real, verified identity. Example: a teacher asking "what subject do I teach" \
becomes `SELECT s.name FROM teaching_assignments ta JOIN grade_subject_offerings gso \
ON gso.id = ta.grade_subject_offering_id JOIN subjects s ON s.id = gso.subject_id \
WHERE ta.teacher_user_id = '__CURRENT_USER_ID__'`. Only use this for a genuine \
self-reference to the asking user — never for any other person the question names or \
implies (a specific student, another teacher), and never when the question doesn't \
need it at all.
- Some tables can legitimately have more than one row per real-world entity you care \
about — most commonly `teaching_assignments` (a teacher who teaches the same subject to \
two sections has two rows sharing one grade_subject_offering_id) and `quiz_attempts` (a \
student who retried a quiz has one row per attempt_number). If you JOIN one of these \
tables only to check that a qualifying row exists — not to read a value specific to \
that one row — add `DISTINCT` to your outer SELECT, or reformulate the join as an \
`EXISTS (...)` subquery. Otherwise the same student can appear more than once in your \
result, once per matching row, even though the answer should count or list them once.
- Prefer the simplest join path that actually answers the question. Only join through \
`topics`, `subtopics`, `questions`, `question_versions`, `common_mastery_quizzes`, or \
`quiz_versions` when the question genuinely needs curriculum-specific data (a topic \
name, a specific quiz's identity, a question bank count) that has no simpler \
equivalent — for example, filtering by *subject* only needs the `subjects` table \
(never `topics`), and filtering by whether a quiz was passed only needs \
`quiz_attempts.passed` (never `quiz_versions`). These curriculum tables are currently \
refused outright by a later step regardless of role, so routing through one \
unnecessarily turns an answerable question into a refusal.
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

"""LangGraph wire-format state for the text-to-SQL pipeline.

`TextToSQLState` mirrors the pattern in `modules/assistant/graph.py`'s `GraphState`:
a loose, `total=False` TypedDict, since LangGraph nodes return partial updates that
get merged into the running state rather than replacing it wholesale.
"""

from __future__ import annotations

from typing import Any, Final, TypedDict

# retry_count starts at 0 (set by whatever builds the initial state) and is capped
# here; graph.py's routing checks against this when deciding retry vs. honest_refusal.
MAX_RETRIES: Final[int] = 3


# --- state["error"] class convention ------------------------------------------------
#
# Every node that sets state["error"] must format it with `format_error()` below, using
# exactly one of these three category constants. This is the single documented
# contract for classifying a failure — nodes that produce an error and nodes that
# consume one (audit_log, honest_refusal, and eventually compose_answer) all key off
# the same fixed prefixes instead of each inventing their own wording to grep for.
# `error_category()` is the matching consumer-side helper; use it rather than hand-
# rolling another `.startswith(...)` check.
#
# This is deliberately just three string constants plus two tiny functions, not a
# structured error type — `state["error"]` stays `str | None`. A real typed error
# object would be the next step if/when more than these three categories, or fields
# beyond a category + message, turn out to be needed; not warranted yet.

LLM_ERROR: Final[str] = "LLM_ERROR"
"""The LLM/API call itself failed — network error, auth failure, empty completion,
rate limit, missing OPENROUTER_API_KEY. No SQL/answer was produced at all; this is not
the model producing bad output, so there is nothing to hand back to it as a correction
in a retry prompt. Raised by generate_sql today."""

VALIDATION_ERROR: Final[str] = "VALIDATION_ERROR"
"""The LLM produced SQL, but it was rejected — bad syntax, a disallowed statement type,
or a reference to a table/column not present in schema_context. The rejection reason
belongs in the next retry's prompt (see generate_sql's retry handling). Raised by
validate_sql."""

ROLE_VIOLATION: Final[str] = "ROLE_VIOLATION"
"""The SQL is fine on its own terms, but apply_role_scope determined the asking
user_role isn't allowed to run or see it — a policy rejection, not a correctness one.
Raised by apply_role_scope."""

_ERROR_CATEGORIES: Final[frozenset[str]] = frozenset({LLM_ERROR, VALIDATION_ERROR, ROLE_VIOLATION})


def format_error(category: str, detail: str) -> str:
    """Build a `state["error"]` value with the shared category prefix. Always use this
    to set state["error"] rather than formatting the string by hand, so the prefix
    convention can't drift (typo'd colon/spacing, category not in `_ERROR_CATEGORIES`).
    """
    if category not in _ERROR_CATEGORIES:
        raise ValueError(
            f"unknown error category {category!r}; must be one of {sorted(_ERROR_CATEGORIES)}"
        )
    return f"{category}: {detail}"


def error_category(error: str | None) -> str | None:
    """The category a `state["error"]` value was formatted with, or `None` if `error`
    is unset or wasn't produced by `format_error()` (e.g. legacy/foreign text).
    """
    if error is None:
        return None
    category, _, _rest = error.partition(": ")
    return category if category in _ERROR_CATEGORIES else None


class TextToSQLState(TypedDict, total=False):
    """State threaded node to node through the text-to-SQL graph (see graph.py)."""

    # --- Input, set once at graph invocation ---
    question: str  # the user's natural-language question
    user_id: str
    user_role: str  # one of: "admin", "teacher", "student", "parent" — drives apply_role_scope
    institution_id: str  # same sourcing discipline as user_id/user_role: populated once,
    # upstream, from the verified JWT/session — never from the question, LLM output, or
    # any other untrusted input. apply_role_scope pins every sensitive-table read to this
    # tenant, for every role including admin.
    schema_context: str  # schema catalog markdown, loaded by load_schema from schema_catalog.md
    query_source: str | None  # "template" (apply_role_scope skips its AST rewrite —
    # the template author already wrote the row-scoping logic into the template SQL) or
    # None/unset for the default free-form path (generate_sql's LLM output), which gets
    # the full apply_role_scope rewrite. No template caller exists yet; this is here for
    # a future template-based task.

    # --- SQL generation / validation ---
    generated_sql: str | None  # raw SQL produced by generate_sql, before validation
    validated_sql: str | None  # SQL that passed validate_sql; only set once safe to run
    retry_count: int  # number of generate_sql attempts so far; default 0, capped at MAX_RETRIES

    # --- Execution ---
    query_result: list[dict[str, Any]] | None  # rows returned by execute_sql
    result_row_count: int | None

    # --- Output ---
    natural_answer: str | None  # final natural-language answer composed by compose_answer
    confidence: str | None  # one of: "high", "medium", "low"
    provenance: str | None  # human-readable trace of what was queried

    # --- Error handling / audit ---
    error: str | None  # set by any node that fails
    audit_entry: dict[str, Any] | None  # structured record written by audit_log

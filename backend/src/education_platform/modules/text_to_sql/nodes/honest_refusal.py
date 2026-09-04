"""Turns a failure already decided upstream into state["natural_answer"] — phrasing
only, no routing decisions. Reached from every failure branch in graph.py:
injection_guard's INJECTION_BLOCKED and OFF_TOPIC_REJECTED, load_schema's SCHEMA_ERROR,
validate_sql's "refuse" edge (retries exhausted), apply_role_scope's ROLE_VIOLATION,
execute_sql's EXECUTION_ERROR, and audit_log's own fail-closed AUDIT_ERROR path.

**Message per category**, honest about *what kind* of failure occurred without exposing
*how*: `LLM_ERROR` (the AI service itself failed — try again) and `VALIDATION_ERROR`
(couldn't produce a safe query after retries — try rephrasing) get distinct wording
because they suggest different next actions to the user. `ROLE_VIOLATION` gets its own
message too ("touches data you don't have access to") — deliberately not phrased the same
as the infrastructure failures below it, since "you're not allowed to see this" and "our
system broke" are different facts a user should be able to tell apart. `INJECTION_BLOCKED`
also gets its own distinct wording ("ask a concrete question...") rather than reusing
`ROLE_VIOLATION`'s, for the same reason in reverse: this question was never evaluated
against real data at all, so "you don't have access to this" would be a false claim about
something that was never checked — one fixed message regardless of which of
injection_guard's three internal reasons (heuristic match, classifier match, classifier
unavailable) produced it, matching every other category's "no internals in the
user-facing text" rule; the specific reason still reaches the audit trail via
`state["error"]`'s full detail text, just not this message. `OFF_TOPIC_REJECTED` gets its
own message too, distinct from `INJECTION_BLOCKED`'s — "ask something in scope" reads as
neutral guidance, not an accusation, which matters here specifically because this category
fires for entirely benign questions ("what's the weather") that were never any kind of
attack; reusing `INJECTION_BLOCKED`'s wording would misrepresent a scope mismatch as a
security refusal. `SCHEMA_ERROR`,
`EXECUTION_ERROR`, and `AUDIT_ERROR` share one generic message: all three are
infrastructure failures, not anything the user did wrong, and none is a case where "try
rephrasing" would help — `EXECUTION_ERROR`/`AUDIT_ERROR` because the query was already
valid and authorized by the time either fired, `SCHEMA_ERROR` because no query was even
attempted yet — the catalog file itself is unusable, which rephrasing the question can't
fix either.

**Never leaks internals**: every message here is a fixed constant, never built from
`state["error"]`'s own text, `state["generated_sql"]`/`validated_sql`, table/column
names, retry counts, or node names — the same discipline `execute_sql` (Task 7) and
`compose_answer` (Task 9) already apply to their own user-facing text, inherited rather
than relaxed here. `state["error"]` itself is deliberately left untouched (see below) —
its raw text stays internal to `state`, read only by `error_category()` here, never
copied into `natural_answer`.

**Never raises.** This is the last node before a response goes back to the user on every
failure path; if it breaks, there is nowhere left to catch it. Provably exception-free by
construction rather than wrapped in a defensive `try/except`: every read is `state.get()`
with a default, `_MESSAGES.get(category, _GENERIC_MESSAGE)` never raises on an unrecognized
or `None` category (including `error_category()` returning `None` for `state["error"]`
being unset entirely, or for any future error text that doesn't follow the
`format_error()` convention — every node in this pipeline follows it today, load_schema
included, but this fallback stays regardless: a category consumer should never assume a
category producer can't regress), and nothing here does I/O, parses anything, or calls
another system. A blanket `try/except Exception` would only hide a real bug in this
trivial logic during development, not add genuine safety over code that cannot fail on
its own terms.

**state["confidence"]**: sanity_check (Task 8) only ever runs after execute_sql's success
edge, so every path that reaches honest_refusal never had sanity_check touch confidence at
all — it's still whatever the initial state set it to (`None` in every caller so far).
Set to `"low"` here if not already set, reusing the existing high/medium/low scale rather
than inventing a fourth value state.py doesn't declare — "low" is the correct end of that
scale for "do not treat this as a trustworthy answer," which is exactly what a refusal is.

**state["error"] is never overwritten.** audit_log (Task 10) runs after this node on every
path and needs the *original* category to record the real failure reason, not a generic
"refused" — see audit_log.py's own payload, which records `error_category`/`error_detail`
straight from `state["error"]`. Overwriting it here would make every refusal's audit
record indistinguishable regardless of why it happened.
"""

from __future__ import annotations

from typing import Final

from education_platform.modules.text_to_sql.state import (
    AUDIT_ERROR,
    EXECUTION_ERROR,
    INJECTION_BLOCKED,
    LLM_ERROR,
    OFF_TOPIC_REJECTED,
    ROLE_VIOLATION,
    SCHEMA_ERROR,
    VALIDATION_ERROR,
    TextToSQLState,
    error_category,
)

_GENERIC_MESSAGE: Final[str] = "Something went wrong on our end — please try again."

_MESSAGES: Final[dict[str, str]] = {
    SCHEMA_ERROR: _GENERIC_MESSAGE,
    LLM_ERROR: (
        "I wasn't able to reach the AI service to answer that question — please try "
        "again in a moment."
    ),
    VALIDATION_ERROR: (
        "I wasn't able to turn that into a safe query after a few attempts — try "
        "rephrasing your question."
    ),
    ROLE_VIOLATION: "That question touches data you don't have access to.",
    EXECUTION_ERROR: _GENERIC_MESSAGE,
    AUDIT_ERROR: _GENERIC_MESSAGE,
    INJECTION_BLOCKED: (
        "I can't process that request. Please ask a concrete question about your "
        "students, classes, or school data."
    ),
    OFF_TOPIC_REJECTED: (
        "I can only help with questions about your school's students, classes, "
        "attendance, or curriculum data. Try asking something in that scope."
    ),
}

_FAILURE_CONFIDENCE: Final[str] = "low"


async def honest_refusal(state: TextToSQLState) -> TextToSQLState:
    category = error_category(state.get("error"))
    message = _MESSAGES.get(category, _GENERIC_MESSAGE) if category else _GENERIC_MESSAGE

    return {
        **state,
        "natural_answer": message,
        "confidence": state.get("confidence") or _FAILURE_CONFIDENCE,
    }

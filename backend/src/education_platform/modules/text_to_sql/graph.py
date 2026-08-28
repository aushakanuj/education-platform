"""Text-to-SQL LangGraph skeleton: structure and routing only, no node logic yet.

Happy path:

    load_schema -> generate_sql -> validate_sql -> apply_role_scope -> execute_sql
        -> sanity_check -> compose_answer -> audit_log -> END

honest_refusal is reached from four independent failure branches, none of which loop back
into generate_sql's retry path: load_schema's "error", validate_sql's "refuse" once
retries are exhausted, apply_role_scope's ROLE_VIOLATION, and execute_sql's
EXECUTION_ERROR. Only validate_sql's own "retry" edge goes back to generate_sql, and only
while retry_count < MAX_RETRIES — see `_route_after_validate` and `MAX_RETRIES`.
honest_refusal itself then also feeds into audit_log, same as compose_answer, so refusals
get logged too.

Most nodes in `modules/text_to_sql/nodes/` are still pass-through placeholders (see that
package's docstring); `load_schema`, `generate_sql`, `validate_sql`, `apply_role_scope`,
`execute_sql`, `sanity_check`, `compose_answer`, `audit_log`, and `honest_refusal` are
implemented, so the routing functions for those stages inspect real signals. The rest
fall back to fixed placeholder decisions, each flagged with a TODO for the follow-up task
that implements the remaining node logic.

Note on `honest_refusal` and `audit_log`: `audit_log`'s own fail-closed path (Task 10,
`AUDIT_ERROR`) does not route back through `honest_refusal` — `audit_log` runs strictly
after it on every path (see the edges below: `honest_refusal -> audit_log -> END`,
unconditional), so it produces its own refusal text directly rather than looping back.
`honest_refusal` still formats a message for `AUDIT_ERROR` as one of its five categories,
for defensive completeness and direct-invocation testing, but that branch is not
reachable through the compiled graph today.
"""

from __future__ import annotations

from typing import Literal

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from education_platform.modules.text_to_sql.nodes import (
    apply_role_scope,
    audit_log,
    compose_answer,
    execute_sql,
    generate_sql,
    honest_refusal,
    load_schema,
    sanity_check,
    validate_sql,
)
from education_platform.modules.text_to_sql.state import MAX_RETRIES, TextToSQLState


def _route_after_load_schema(state: TextToSQLState) -> Literal["ok", "error"]:
    # load_schema sets state["error"] (not raise) when schema_catalog.md is missing or
    # the excluded-content filter fails its own post-check — never proceed to
    # generate_sql with a broken/absent schema_context.
    return "error" if state.get("error") else "ok"


def _route_after_validate(state: TextToSQLState) -> Literal["retry", "refuse", "valid"]:
    if state.get("validated_sql"):
        return "valid"
    if state.get("retry_count", 0) < MAX_RETRIES:
        return "retry"
    return "refuse"


def _route_after_apply_role_scope(state: TextToSQLState) -> Literal["ok", "refuse"]:
    # apply_role_scope sets state["error"] (ROLE_VIOLATION) when the query is rejected on
    # authorization grounds — a policy rejection, not a correctness one, so it must never
    # loop back through generate_sql's retry path; it goes straight to honest_refusal,
    # same as a validate_sql retry-exhaustion refusal.
    return "refuse" if state.get("error") else "ok"


def _route_after_execute(state: TextToSQLState) -> Literal["ok", "refuse"]:
    # execute_sql sets state["error"] (EXECUTION_ERROR) on a genuine DB-level failure —
    # timeout, connection failure, unexpected constraint violation. The SQL was already
    # proven valid and authorized by the time it got here, so generate_sql rewriting it
    # again can't fix a database failure; this goes straight to honest_refusal, same as
    # a validate_sql/apply_role_scope rejection, never back into the retry loop.
    return "refuse" if state.get("error") else "ok"


def _route_after_sanity_check(state: TextToSQLState) -> Literal["suspicious", "normal"]:
    # sanity_check (Task 8) is the sole owner of state["confidence"] — it's fully decided
    # there, not by this router or by which node runs next. "medium" and "low" both route
    # via "suspicious": nothing downstream currently behaves differently between them
    # (compose_answer reads state["confidence"] directly for its own phrasing, not the
    # edge that was taken), so collapsing them here loses no information. See
    # sanity_check.py's module docstring for the full reasoning.
    return "normal" if state.get("confidence") == "high" else "suspicious"


def build_text_to_sql_graph() -> CompiledStateGraph[TextToSQLState, None, TextToSQLState]:
    graph: StateGraph[TextToSQLState] = StateGraph(TextToSQLState)

    graph.add_node("load_schema", load_schema)
    graph.add_node("generate_sql", generate_sql)
    graph.add_node("validate_sql", validate_sql)
    graph.add_node("apply_role_scope", apply_role_scope)
    graph.add_node("execute_sql", execute_sql)
    graph.add_node("sanity_check", sanity_check)
    graph.add_node("compose_answer", compose_answer)
    graph.add_node("audit_log", audit_log)
    graph.add_node("honest_refusal", honest_refusal)

    graph.set_entry_point("load_schema")
    graph.add_conditional_edges(
        "load_schema",
        _route_after_load_schema,
        {
            "ok": "generate_sql",
            "error": "honest_refusal",
        },
    )
    graph.add_edge("generate_sql", "validate_sql")

    graph.add_conditional_edges(
        "validate_sql",
        _route_after_validate,
        {
            "retry": "generate_sql",
            "refuse": "honest_refusal",
            "valid": "apply_role_scope",
        },
    )

    graph.add_conditional_edges(
        "apply_role_scope",
        _route_after_apply_role_scope,
        {
            "ok": "execute_sql",
            "refuse": "honest_refusal",
        },
    )
    graph.add_conditional_edges(
        "execute_sql",
        _route_after_execute,
        {
            "ok": "sanity_check",
            "refuse": "honest_refusal",
        },
    )

    # Both keys route to the same node: sanity_check already decided state["confidence"]
    # ("medium" and "low" both take the "suspicious" edge — see _route_after_sanity_check).
    # Kept as a conditional edge with two named keys, rather than a single add_edge,
    # purely for graph-shape/trace readability — there is deliberately no glue node here
    # anymore to set confidence, since sanity_check already did.
    graph.add_conditional_edges(
        "sanity_check",
        _route_after_sanity_check,
        {
            "suspicious": "compose_answer",
            "normal": "compose_answer",
        },
    )

    graph.add_edge("compose_answer", "audit_log")
    graph.add_edge("honest_refusal", "audit_log")
    graph.add_edge("audit_log", END)

    return graph.compile()

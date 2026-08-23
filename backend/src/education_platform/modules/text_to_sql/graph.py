"""Text-to-SQL LangGraph skeleton: structure and routing only, no node logic yet.

Pipeline shape:

    load_schema -> generate_sql -> validate_sql
         |              ^                | valid -> apply_role_scope -> execute_sql -> sanity_check
         | load failed  | retry          | invalid, retries exhausted        |                |
         +-------------------------------+-> honest_refusal <---------------+  suspicious/normal
                                                |          role violation                       |
                                                +-------------------> compose_answer <-----------+
                                                                            |
                                                                        audit_log -> END

Most nodes in `modules/text_to_sql/nodes/` are still pass-through placeholders (see that
package's docstring); `load_schema`, `generate_sql`, `validate_sql`, and `apply_role_scope`
are implemented, so the routing functions for those stages inspect real signals. The rest
fall back to fixed placeholder decisions, each flagged with a TODO for the follow-up task
that implements the remaining node logic.
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


def _route_after_sanity_check(state: TextToSQLState) -> Literal["suspicious", "normal"]:
    # TODO(sanity_check): once sanity_check actually inspects query_result for
    # anomalies, route off that signal instead of defaulting to "normal".
    return "suspicious" if state.get("error") else "normal"


async def _mark_confidence_low(state: TextToSQLState) -> TextToSQLState:
    # LangGraph conditional-edge routers can only select a destination node, not also
    # update state — so the "with low/high confidence" half of the sanity_check
    # routing needs a tiny node of its own to actually write state["confidence"].
    # This is graph-wiring glue, not one of the nine domain nodes.
    return {**state, "confidence": "low"}


async def _mark_confidence_high(state: TextToSQLState) -> TextToSQLState:
    return {**state, "confidence": "high"}


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
    graph.add_node("_mark_confidence_low", _mark_confidence_low)
    graph.add_node("_mark_confidence_high", _mark_confidence_high)

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
    graph.add_edge("execute_sql", "sanity_check")

    graph.add_conditional_edges(
        "sanity_check",
        _route_after_sanity_check,
        {
            "suspicious": "_mark_confidence_low",
            "normal": "_mark_confidence_high",
        },
    )
    graph.add_edge("_mark_confidence_low", "compose_answer")
    graph.add_edge("_mark_confidence_high", "compose_answer")

    graph.add_edge("compose_answer", "audit_log")
    graph.add_edge("honest_refusal", "audit_log")
    graph.add_edge("audit_log", END)

    return graph.compile()

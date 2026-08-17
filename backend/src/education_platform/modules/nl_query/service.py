"""Task 2.2 — turn an English question into a query, run it, show the working.

The flow is deliberately linear and every step is inspectable:

    question -> model writes SQL -> guardrail rewrites it -> read-only execution -> rows

The model is reached through an injected callable rather than imported directly, so the
tests drive the whole path -- guardrail, execution, audit -- without calling a paid API.
That is the difference between testing the plumbing and testing the prompt.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from education_platform.db.session import get_engine
from education_platform.modules.assistant.openrouter import OpenRouterError, chat_completion_json
from education_platform.modules.authorization.scope import Scope
from education_platform.modules.insights.service import MAX_ROWS
from education_platform.modules.nl_query import catalog
from education_platform.modules.nl_query.guardrail import (
    STATEMENT_TIMEOUT_MS,
    GuardrailViolation,
    guard,
)

#: Signature of "ask the model for SQL". Injected so tests never reach the network.
SqlWriter = Callable[[str], Awaitable["ModelReply"]]


@dataclass(frozen=True, slots=True)
class ModelReply:
    sql: str | None
    #: Set when the model judged the question unanswerable from this data.
    declined: str | None = None


@dataclass(slots=True)
class QueryAnswer:
    question: str
    answered: bool
    #: Plain-English explanation when `answered` is False. Never a stack trace.
    reason: str | None = None
    model_sql: str | None = None
    executed_sql: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    row_count: int = 0
    truncated: bool = False


SYSTEM_PROMPT = (
    "You translate a question about a school into one PostgreSQL SELECT query.\n\n"
    'Reply with JSON only: {"sql": "<the query>"} when you can answer, or '
    '{"unanswerable": "<one sentence saying what is missing>"} when the data below '
    "cannot answer it.\n\n"
    "Decline rather than guess. A question about fees, timetables, behaviour, staff pay or "
    "anything absent from the columns below is unanswerable -- say so plainly instead of "
    "inventing a column.\n\n" + catalog.render_catalog()
)


async def _openrouter_writer(question: str) -> ModelReply:
    payload = await chat_completion_json(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        temperature=0.0,
    )
    declined = payload.get("unanswerable")
    sql = payload.get("sql")
    return ModelReply(
        sql=str(sql) if sql else None,
        declined=str(declined) if declined else None,
    )


def _jsonable(value: Any) -> Any:
    """Postgres returns Decimal, UUID and datetime; JSON does not take them."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


async def _run_readonly(sql: str) -> tuple[list[str], list[list[Any]]]:
    """Execute generated SQL on its own connection, read-only, with a timeout.

    A separate connection keeps the request's session out of reach: whatever the query
    does, it cannot see or disturb uncommitted work such as the audit entry being written
    alongside it. READ ONLY is enforced by PostgreSQL, which is the point -- it holds even
    if every check above it were bypassed.

    `exec_driver_sql`, not `text()`: the generated SQL contains `::UUID` casts, and
    `text()` would read `:UUID` as a bind parameter and fail.
    """
    engine = get_engine()
    connection: AsyncConnection
    async with engine.connect() as connection:
        await connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        await connection.exec_driver_sql(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}")
        result = await connection.exec_driver_sql(sql)
        columns = list(result.keys())
        rows = [[_jsonable(value) for value in row] for row in result.fetchall()]
    return columns, rows


async def answer_question(
    question: str,
    scope: Scope,
    *,
    row_limit: int = MAX_ROWS,
    write_sql: SqlWriter | None = None,
) -> QueryAnswer:
    """Answer `question` within `scope`, or explain plainly why it cannot be answered."""
    asked = question.strip()
    if not asked:
        return QueryAnswer(question=question, answered=False, reason="Ask a question first.")

    writer = write_sql or _openrouter_writer
    try:
        reply = await writer(asked)
    except OpenRouterError as exc:
        return QueryAnswer(question=asked, answered=False, reason=str(exc))

    if reply.declined or not reply.sql:
        return QueryAnswer(
            question=asked,
            answered=False,
            reason=reply.declined or "The model did not produce a query.",
        )

    try:
        guarded = guard(reply.sql, scope, row_limit=row_limit)
    except GuardrailViolation as exc:
        return QueryAnswer(
            question=asked,
            answered=False,
            reason=exc.reason,
            model_sql=reply.sql,
        )

    try:
        columns, rows = await _run_readonly(guarded.executed_sql)
    except Exception as exc:  # noqa: BLE001 — a bad generated query must not 500 the API
        return QueryAnswer(
            question=asked,
            answered=False,
            reason=f"The query could not be run: {type(exc).__name__}.",
            model_sql=guarded.model_sql,
            executed_sql=guarded.executed_sql,
        )

    return QueryAnswer(
        question=asked,
        answered=True,
        model_sql=guarded.model_sql,
        executed_sql=guarded.executed_sql,
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=len(rows) >= guarded.row_limit,
    )

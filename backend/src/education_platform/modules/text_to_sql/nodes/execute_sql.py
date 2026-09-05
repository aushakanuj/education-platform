"""Executes state["validated_sql"] — already validated (Task 5) and role/institution
scoped (Task 6) — against Postgres, and populates state["query_result"]/
state["result_row_count"].

Connects as the restricted `text_to_sql_reader` DB role (see
`db.session.get_text_to_sql_engine` / migration `c9d0e1f2a3b4`), not the application's own
`education` role — SELECT-only, granted on exactly `load_schema.REQUIRED_TABLES`, with
`users.password_hash`/`refresh_sessions.token_hash` excluded at the column-privilege level
and `question_answer_keys` excluded entirely. This is deliberate defense-in-depth,
independent of Task 5's structural whitelist and Task 6's row/column/institution scoping:
if either of those has an undiscovered bug, a query that reaches this node still cannot
read a column or table it wasn't granted, or write anything at all, regardless of what SQL
text made it this far.

Three more layers enforced here, at the database connection itself rather than in Python:

* **Row-Level Security identity propagation** (migration `e1f2a3b4c5d6`) — the 5th
  defense-in-depth layer, and the one that still holds if `apply_role_scope` (Task 6) has
  a bug nobody's found yet: RLS policies on every scoped table re-derive the same row-
  visibility rule that node already computed, enforced inside Postgres itself regardless
  of what SQL text arrives. Those policies read three session variables —
  `app.current_user_id`/`app.current_user_role`/`app.current_institution_id` — that only
  this node sets, via `set_config(..., true)` (the parameterized equivalent of
  `SET LOCAL`, chosen over string-interpolating a `SET LOCAL` statement so these values
  go through the driver's normal bind-parameter path like any other untrusted-shaped
  string, even though they're already sourced from the same verified `state["user_id"]`/
  `state["user_role"]`/`state["institution_id"]` fields every other node in this pipeline
  trusts — never from the question or LLM output). The `true` third argument is what
  makes each `set_config` call transaction-scoped, identical to `SET LOCAL`: it can never
  leak onto a pooled connection some other session picks up next. If this node were ever
  skipped or reached with these fields unset, every RLS policy's `current_setting(name,
  true)` read comes back NULL, which satisfies no equality check — the policies deny by
  default (zero rows), not "fall back to unscoped," so a bug here fails toward less
  access, not more.
* **Statement timeout** (`STATEMENT_TIMEOUT_MS`) — set via `SET LOCAL` inside the same
  transaction as the query, so a malformed or unexpectedly expensive query (a bad join
  fan-out, a missing index) is cancelled by Postgres itself rather than hanging this node,
  the event loop, or degrading the database for other users. `SET LOCAL` (not plain `SET`)
  matters: it only lasts for the current transaction, so it can never leak onto a pooled
  connection some other query picks up next.
* **Row cap, belt-and-suspenders** (`ROW_CAP` — imported as
  `validate_sql.DEFAULT_ROW_LIMIT`, not a second literal `500`, so the two can't silently
  drift apart) — validate_sql already injects `LIMIT 500` onto the root SELECT if the
  model's SQL didn't have one, and that structurally bounds the outermost result set, not
  just some subquery's. This node still doesn't fully trust that: if the row count ever
  exceeds `ROW_CAP` anyway (a bug in that injection, an apply_role_scope rewrite that
  somehow dropped the LIMIT, ...), the rows are truncated to `ROW_CAP` rather than either
  trusted as-is or turned into a hard failure — truncating is the direction that can never
  return more than intended, and a purely defensive over-count shouldn't turn what is
  otherwise a fine answer into a user-facing refusal. Logged as a warning either way, since
  it means validate_sql's own guarantee didn't hold.

Failure handling: any `SQLAlchemyError` here (timeout, connection failure, an unexpected
constraint violation) is a genuine execution failure, not a correctness or authorization
one — the SQL was already proven valid and authorized by the time it reaches this node.
`state["error"]` is always the same generic, user-safe text; the real exception (which can
carry schema/constraint names or fragments of the query) goes to `logger` and to
`state["audit_entry"]` only, never into the user-facing error string. `state["retry_count"]`
is never touched — generate_sql can't fix a database-level failure by rewriting SQL, so
this routes to honest_refusal (see graph.py's `_route_after_execute`), never back into the
retry loop.
"""

from __future__ import annotations

import logging
from typing import Any, Final

from sqlalchemy import Uuid, bindparam, text
from sqlalchemy.exc import SQLAlchemyError

from education_platform.db.session import get_text_to_sql_session_factory
from education_platform.modules.text_to_sql.nodes.validate_sql import (
    DEFAULT_ROW_LIMIT as ROW_CAP,
)
from education_platform.modules.text_to_sql.state import (
    EXECUTION_ERROR,
    TextToSQLState,
    format_error,
)

logger = logging.getLogger(__name__)

# ROW_CAP is a rename-on-import (from validate_sql.DEFAULT_ROW_LIMIT), which mypy's
# implicit-reexport check (implied by `strict = true`) doesn't treat as re-exported by
# default — sanity_check.py imports it from here deliberately (see its own docstring:
# "the cap that was actually applied to the executed result"), so it needs to be listed
# explicitly.
__all__ = ["execute_sql", "ROW_CAP"]

STATEMENT_TIMEOUT_MS: Final[int] = 5_000

_GENERIC_FAILURE_MESSAGE: Final[str] = "the query could not be run"


async def execute_sql(state: TextToSQLState) -> TextToSQLState:
    sql = state.get("validated_sql")
    if not sql:
        # Graph invariant: this node only runs after apply_role_scope's "ok" edge, which
        # guarantees a non-empty validated_sql. Fail loudly rather than execute nothing
        # and silently report success if that invariant is ever violated.
        return {
            **state,
            "query_result": None,
            "result_row_count": None,
            "error": format_error(EXECUTION_ERROR, "execute_sql: no validated_sql to run"),
        }

    session_factory = get_text_to_sql_session_factory()
    try:
        async with session_factory() as session:
            # Must run before the query itself: RLS policies read these on every table
            # access, so they need to already be set by the time `sql` executes, in the
            # same transaction (SQLAlchemy's async session keeps one transaction open
            # across these statements by default, same as the existing statement_timeout
            # call below).
            await session.execute(
                text(
                    "SELECT set_config('app.current_user_id', :user_id, true), "
                    "set_config('app.current_user_role', :user_role, true), "
                    "set_config('app.current_institution_id', :institution_id, true)"
                ),
                {
                    "user_id": state["user_id"],
                    "user_role": state["user_role"],
                    "institution_id": state["institution_id"],
                },
            )
            await session.execute(text(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}"))
            parameters = {
                **(state.get("intent_parameters") or {}),
                "current_user_id": state["user_id"],
                "current_institution_id": state["institution_id"],
            }
            unbound_statement = text(sql)
            required_parameters = {
                name: parameters[name]
                for name in unbound_statement._bindparams
                if name in parameters
            }
            # current_user_id/current_institution_id are always uuid columns on the
            # scoped tables they're compared against (teacher_user_id, institution_id,
            # ...). Without an explicit type here, asyncpg sends a plain Python str as
            # $N::VARCHAR, and Postgres has no `uuid = character varying` operator for a
            # bound (as opposed to literal) parameter -- confirmed live: every template
            # filtering on :current_user_id/:current_institution_id fails with
            # asyncpg.exceptions.UndefinedFunctionError before this fix.
            _UUID_PARAMS = {"current_user_id", "current_institution_id"}
            statement = unbound_statement.bindparams(
                *(
                    bindparam(name, value=value, type_=Uuid() if name in _UUID_PARAMS else None)
                    for name, value in required_parameters.items()
                )
            )
            result = await session.execute(statement, required_parameters)
            rows: list[dict[str, Any]] = [dict(row) for row in result.mappings().all()]
    except SQLAlchemyError as exc:
        # Postgres/driver error text can carry schema, constraint, or query fragments —
        # it goes to the log and the (internal-only) audit entry, never into
        # state["error"], which is the eventually user-facing value.
        logger.warning(
            "execute_sql: query failed: type=%s detail=%s cause=%s orig=%s",
            type(exc).__name__,
            str(exc),
            str(exc.__cause__) if exc.__cause__ else None,
            str(exc.orig) if getattr(exc, "orig", None) else None,
            exc_info=True,
        )
        return {
            **state,
            "query_result": None,
            "result_row_count": None,
            "error": format_error(EXECUTION_ERROR, _GENERIC_FAILURE_MESSAGE),
            "audit_entry": {
                **(state.get("audit_entry") or {}),
                "execution_error_type": type(exc).__name__,
                "execution_error_detail": str(exc),
                "execution_error_cause": str(exc.__cause__) if exc.__cause__ else None,
                "execution_dbapi_type": (
                    type(exc.orig).__name__ if getattr(exc, "orig", None) else None
                ),
                "execution_dbapi_detail": (
                    str(exc.orig) if getattr(exc, "orig", None) else None
                ),
            },
        }

    if len(rows) > ROW_CAP:
        logger.warning(
            "execute_sql: result had %d rows, exceeding ROW_CAP=%d despite validate_sql's "
            "LIMIT injection — truncating",
            len(rows),
            ROW_CAP,
        )
        rows = rows[:ROW_CAP]
        return {
            **state,
            "query_result": rows,
            "result_row_count": len(rows),
            "error": None,
            "audit_entry": {**(state.get("audit_entry") or {}), "row_cap_truncated": True},
        }

    return {
        **state,
        "query_result": rows,
        "result_row_count": len(rows),
        "error": None,
    }

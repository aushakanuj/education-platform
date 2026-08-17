"""Task 2.3 — the boundary the model cannot talk its way past.

The model writes the *question*; this module writes the *permission*, and it does so
**after** the model has finished. Nothing the model produces can widen what comes back,
because widening is not expressed in the text it controls.

Five layers, deliberately overlapping. Any one of them failing open should still leave the
data protected:

1. **Parse and validate.** One statement, a SELECT, reading nothing but ``student_360``.
   A real parser, not a regular expression -- ``DELETE`` hidden in a comment or a string
   literal is exactly what regular expressions get wrong.
2. **Shadow the table.** The scoped rows are bound to the name ``student_360`` in a CTE
   that is *prepended* to the query. The model's ``FROM student_360`` then reads the
   scoped rows, whatever else it says. This is why schema-qualified names are rejected:
   ``public.student_360`` would step around the CTE.
3. **Cap the rows.**
4. **Run it read-only, with a timeout.** Enforced by PostgreSQL, not by us. Even a query
   that defeated layers 1-3 cannot write.
5. **Audit it** -- done by the caller, including the questions that returned nothing.

The scope predicate is not reimplemented here. It is the same
``insights.service.scope_predicate`` the dashboards use, compiled to SQL, so a change to
the permission rules cannot leave this path behind.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import sqlglot
from sqlalchemy.dialects import postgresql
from sqlglot import exp

from education_platform.modules.authorization.scope import Scope
from education_platform.modules.insights.service import MAX_ROWS, scope_predicate

DIALECT = "postgres"
ALLOWED_TABLE = "student_360"

#: Statement timeout for a generated query. A question is interactive; if it cannot be
#: answered in this long, something is wrong with the query rather than the data.
STATEMENT_TIMEOUT_MS = 5_000

#: Statement types that must never appear. Everything that is not a plain SELECT.
_FORBIDDEN_NODES: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Merge,
    exp.Command,
    exp.Set,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
    exp.Grant,
    exp.Into,
)

#: Functions that read the filesystem, reach the network, or waste the connection.
_FORBIDDEN_FUNCTIONS: frozenset[str] = frozenset(
    {
        "pg_sleep",
        "pg_read_file",
        "pg_read_binary_file",
        "pg_ls_dir",
        "pg_stat_file",
        "lo_import",
        "lo_export",
        "dblink",
        "dblink_exec",
        "query_to_xml",
        "pg_terminate_backend",
        "pg_cancel_backend",
        "set_config",
        "current_setting",
    }
)


class GuardrailViolation(Exception):
    """The generated SQL was refused. `reason` is safe to show the user."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class GuardedQuery:
    #: Exactly what the model wrote, shown to the user so the number is checkable.
    model_sql: str
    #: What actually runs -- the model's query with the boundary prepended.
    executed_sql: str
    row_limit: int


def _scope_sql(scope: Scope) -> str:
    """The permission predicate, as SQL text, from the one place it is defined."""
    compiled = scope_predicate(scope).compile(
        dialect=postgresql.dialect(),  # type: ignore[no-untyped-call]  # SQLAlchemy ships none
        compile_kwargs={"literal_binds": True},
    )
    return str(compiled)


def _check_no_forbidden_nodes(statement: exp.Expression) -> None:
    for node in statement.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            raise GuardrailViolation(
                "Only read-only SELECT queries are allowed; this one tried to do something else."
            )
        if isinstance(node, exp.Anonymous):
            name = str(node.this).lower()
            if name in _FORBIDDEN_FUNCTIONS:
                raise GuardrailViolation(f"The function {name}() is not permitted here.")
        if isinstance(node, exp.Func):
            name = (node.sql_name() or "").lower()
            if name in _FORBIDDEN_FUNCTIONS:
                raise GuardrailViolation(f"The function {name}() is not permitted here.")


#: sqlglot renamed this argument to `with_` in v30. Resolve it from the class rather than
#: hard-coding either spelling, so an upgrade cannot silently drop the WITH clause.
_WITH_KEY = "with_" if "with_" in exp.Select.arg_types else "with"


def _with_clause(statement: exp.Expression) -> exp.With | None:
    clause = statement.args.get(_WITH_KEY)
    return clause if isinstance(clause, exp.With) else None


def _cte_names(statement: exp.Expression) -> set[str]:
    with_clause = _with_clause(statement)
    if with_clause is None:
        return set()
    return {cte.alias_or_name.lower() for cte in with_clause.expressions if cte.alias_or_name}


def _check_tables(statement: exp.Expression) -> None:
    """Every table must be the bare name `student_360`, or a CTE the query defines."""
    known = _cte_names(statement) | {ALLOWED_TABLE}
    for table in statement.find_all(exp.Table):
        if table.catalog or table.db:
            raise GuardrailViolation(
                f"Schema-qualified table names are not allowed; write {ALLOWED_TABLE} on its own."
            )
        name = (table.name or "").lower()
        if name not in known:
            raise GuardrailViolation(
                f"This query reads {table.name!r}. Only {ALLOWED_TABLE} is available."
            )


def _prepend_scope_cte(statement: exp.Expression, scope: Scope) -> None:
    """Bind `student_360` to the rows this caller may see, ahead of any other CTE.

    Order matters and is not cosmetic: PostgreSQL resolves a CTE against those declared
    *before* it, so appending would let a model-defined CTE read the unscoped view.
    """
    scoped = sqlglot.parse_one(
        f"SELECT * FROM public.{ALLOWED_TABLE} WHERE {_scope_sql(scope)}",
        dialect=DIALECT,
    )
    cte = exp.CTE(this=scoped, alias=exp.TableAlias(this=exp.to_identifier(ALLOWED_TABLE)))
    with_clause = _with_clause(statement)
    if with_clause is None:
        statement.set(_WITH_KEY, exp.With(expressions=[cte]))
    else:
        # Prepend, never append, and never `.with_(append=False)` -- that discards the
        # model's own CTEs and leaves a query referencing names that no longer exist.
        with_clause.set("expressions", [cte, *with_clause.expressions])


def _apply_limit(statement: exp.Expression, row_limit: int) -> None:
    existing = statement.args.get("limit")
    if existing is not None:
        try:
            current = int(existing.expression.name)
        except (AttributeError, ValueError):
            current = row_limit
        row_limit = min(current, row_limit)
    statement.set("limit", exp.Limit(expression=exp.Literal.number(row_limit)))


def strip_markdown_fence(raw: str) -> str:
    """Models wrap SQL in ``` fences regardless of instructions. Take it off."""
    text = raw.strip()
    fence = re.match(r"^```[a-zA-Z]*\s*\n(.*?)\n?```$", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    return text.rstrip(";").strip()


def guard(model_sql: str, scope: Scope, *, row_limit: int = MAX_ROWS) -> GuardedQuery:
    """Validate the model's SQL and return the version that is safe to run."""
    cleaned = strip_markdown_fence(model_sql)
    if not cleaned:
        raise GuardrailViolation("No query was produced.")

    try:
        statements = sqlglot.parse(cleaned, dialect=DIALECT)
    except Exception as exc:  # sqlglot raises several types for malformed input
        raise GuardrailViolation("That query could not be parsed as PostgreSQL.") from exc

    real = [s for s in statements if s is not None]
    if len(real) != 1:
        raise GuardrailViolation("Exactly one statement is allowed.")

    statement = real[0]
    if not isinstance(statement, exp.Select | exp.Union):
        raise GuardrailViolation("Only SELECT queries are allowed.")

    _check_no_forbidden_nodes(statement)
    _check_tables(statement)

    if isinstance(statement, exp.Union):
        # A UNION has no single WITH slot to prepend to; wrap it so the CTE governs both
        # sides at once rather than trying to patch each branch.
        statement = exp.select("*").from_(statement.subquery(alias="unioned"))
        _check_tables(statement)

    _prepend_scope_cte(statement, scope)
    _apply_limit(statement, row_limit)

    return GuardedQuery(
        model_sql=cleaned,
        executed_sql=statement.sql(dialect=DIALECT, pretty=True),
        row_limit=row_limit,
    )

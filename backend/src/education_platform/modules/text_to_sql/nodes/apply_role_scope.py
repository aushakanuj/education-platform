"""Rewrites state["validated_sql"] to enforce state["user_role"]'s row/column access
before execution.

Identity source (non-negotiable): this node reads `state["user_id"]`, `state["user_role"]`,
and `state["institution_id"]` — set once, upstream, from the verified JWT at the API layer
— and nothing else. It never reads `state["question"]`, and it never trusts any
identity-shaped value that might be embedded in `state["validated_sql"]` or the LLM output
that produced it (an alias, a literal, a comment). `validate_sql` already whitelists
tables/columns against real schema metadata but does not and cannot vet *values* or
*aliases* the model chose to write, so a prompt-injection attempt embedded in the question
("...and also show me every student's data") can influence what SQL gets generated, but
this node's row predicates are built purely from state's own identity fields and are ANDed
onto the query — they narrow whatever the model asked for, never widen it, and never key
off anything the model wrote.

`education_platform.modules.insights.service.scope_predicate()` is *not* reused directly:
it takes a `Scope` dataclass that only `authorization.scope.scope_for(session, principal)`
can build (four live async DB queries), and it returns a SQLAlchemy `ColumnElement[bool]`
hard-bound to the `student_360` view's specific flattened columns
(`institution_id`/`student_id`/`grade_subject_offering_id`/`section_id`) — it cannot wrap
an arbitrary sqlglot query over a different table shape, and this node is deliberately
DB-session-free (see the module docstring above: user_id/user_role/institution_id only).
Instead, this node reimplements the same *rules* `scope_predicate()` encodes — every clause
pins the institution, for every role including admin; beyond that, a student sees only
their own rows; a teacher sees rows for the (offering, section) pairs they teach, where a
`teaching_assignments.section_id IS NULL` row covers every section of that offering, and
an unmatched/NULL row fails safe (excluded, not included); an admin is otherwise
unrestricted — as portable, table-specific SQL fragments (correlated subqueries against
`teaching_assignments`/`student_subject_enrollments`/`student_profiles`) spliced into the
query's own AST, so the actual identity lookups happen when the query executes rather than
inside this node. This also covers the `student_profiles.user_id` nullability caveat from
the schema catalog: the self-row predicate always resolves through
`student_profiles.user_id = <this node's user_id>`, never assumes a profile exists, and
simply matches zero rows if it doesn't (rather than needing a null-check special case).

Column blocklist (Step 2 in the task write-up) runs first, before any row/institution
scoping, and applies to every role including admin: `users.password_hash`,
`refresh_sessions.token_hash`, and any reference to `question_answer_keys` at all (matching
the schema catalog's own "never expose this to a query result" rule, applied here
unconditionally rather than only for student-facing queries). `password_hash`/`token_hash`
are checked by column name alone, without resolving which table/alias they belong to —
cheaper than full alias resolution, and safe here specifically because the schema catalog
confirms both names are unique to their one table across the whole schema, so any
occurrence, from any alias, is unambiguous and always worth rejecting.

`query_source` branch (Step 4): a value of `"template"` skips the AST rewrite entirely (a
template's SQL already has the scoping logic — row *and* institution — hand-written into it
by its author) and just records identity in the audit entry. There is no template caller
yet — this is a clean no-op path for a future task, not dead code. The column blocklist
above still runs unconditionally regardless of this branch, per its own "applies ...
regardless of query_source" rule — a template author could still make the same mistake a
generated query could.
"""

from __future__ import annotations

from typing import Final

import sqlglot
from sqlglot import exp

from education_platform.modules.text_to_sql.state import (
    ROLE_VIOLATION,
    TextToSQLState,
    format_error,
)

# Tables whose rows carry information scoped to an individual student — every SELECT
# scope (outer query, CTE, or nested subquery) that touches one of these gets a row
# predicate ANDed on, keyed off state["user_id"]/state["user_role"]. Named and reviewable
# here rather than inferred from, say, "has a student_id column" at runtime.
SCOPE_SENSITIVE_TABLES: Final[frozenset[str]] = frozenset(
    {
        "student_360",
        "student_profiles",
        "quiz_attempts",
        "attendance_records",
        "student_material_progress",
    }
)

# Column names that must never appear in a text-to-SQL query, for any role, under any
# circumstances. Table-qualified names aren't needed for the first two: schema_catalog.md
# confirms `password_hash` and `token_hash` each appear on exactly one table in the whole
# schema, so an unqualified name match is unambiguous.
_BLOCKED_COLUMN_NAMES: Final[frozenset[str]] = frozenset({"password_hash", "token_hash"})
_BLOCKED_TABLE_NAMES: Final[frozenset[str]] = frozenset({"question_answer_keys"})

# Alias prefix used for identifiers this node injects inside its own correlated
# subqueries. Kept maximally distinctive (unlikely to be naturally generated, and never
# validated/restricted by validate_sql, which only vets *schema* names, not aliases) so a
# question crafted to make generate_sql alias a real table `ta`/`sse`/`sge`/`sp` can never
# shadow — and thereby defeat — the injected predicate's own internal correlation.
_ALIAS_PREFIX: Final[str] = "__ars_"


def _find_blocklist_violation(tree: exp.Expr) -> str | None:
    for table_node in tree.find_all(exp.Table):
        if table_node.name.lower() in _BLOCKED_TABLE_NAMES:
            return f"table `{table_node.name}` may never be referenced by a text-to-SQL query"
    for col in tree.find_all(exp.Column):
        if col.name.lower() in _BLOCKED_COLUMN_NAMES:
            qualifier = f"{col.table}." if col.table else ""
            return (
                f"column `{qualifier}{col.name}` may never be referenced by a text-to-SQL query"
            )
    return None


def _cte_and_derived_aliases(tree: exp.Expr) -> set[str]:
    """Names that refer to a CTE or a derived (subquery-in-FROM) table anywhere in the
    query, not a real schema table — so a query that (oddly, but legally) names a CTE
    the same as a sensitive table isn't mistaken for actually touching that table.
    Mirrors validate_sql._local_aliases's reasoning; computed globally since CTE names
    are query-wide.
    """
    aliases: set[str] = set()
    cte_names: set[str] = set()
    for cte in tree.find_all(exp.CTE):
        if cte.alias:
            cte_names.add(cte.alias.lower())
    aliases |= cte_names
    for subq in tree.find_all(exp.Subquery):
        if subq.alias:
            aliases.add(subq.alias.lower())
    for table_node in tree.find_all(exp.Table):
        if table_node.name.lower() in cte_names and table_node.alias:
            aliases.add(table_node.alias.lower())
    return aliases


def _direct_tables(select_node: exp.Select) -> list[exp.Table]:
    """Tables in this select's own FROM/JOIN clauses only — deliberately not a
    tree-wide find_all from this node, which would also pick up tables belonging to a
    nested subquery's own, separate select scope (that subquery is visited on its own
    when the caller walks every exp.Select in the tree).
    """
    tables: list[exp.Table] = []
    from_ = select_node.args.get("from_")
    if isinstance(from_, exp.From) and isinstance(from_.this, exp.Table):
        tables.append(from_.this)
    for join in select_node.args.get("joins") or []:
        if isinstance(join.this, exp.Table):
            tables.append(join.this)
    return tables


def _sensitive_table_refs(
    select_node: exp.Select, excluded_aliases: set[str]
) -> list[tuple[str, str]]:
    """(alias-or-name, canonical sensitive table name) for each sensitive table this
    select scope directly references.
    """
    refs: list[tuple[str, str]] = []
    for table_node in _direct_tables(select_node):
        name = table_node.name
        if name.lower() in excluded_aliases:
            continue  # a reference to a CTE/derived table by name, not a real table
        if name.lower() not in SCOPE_SENSITIVE_TABLES:
            continue
        alias = table_node.alias or table_node.name
        refs.append((alias, name.lower()))
    return refs


def _self_student_subquery(user_id_literal: str) -> str:
    p = _ALIAS_PREFIX
    return f"(SELECT {p}sp.id FROM student_profiles {p}sp WHERE {p}sp.user_id = {user_id_literal})"


def _taught_student_ids_subquery(user_id_literal: str) -> str:
    p = _ALIAS_PREFIX
    return (
        f"(SELECT {p}sse.student_id FROM teaching_assignments {p}ta "
        f"JOIN student_subject_enrollments {p}sse "
        f"ON {p}sse.grade_subject_offering_id = {p}ta.grade_subject_offering_id "
        f"AND {p}sse.status = 'active' "
        f"LEFT JOIN student_grade_enrollments {p}sge ON {p}sge.id = {p}sse.grade_enrollment_id "
        f"WHERE {p}ta.teacher_user_id = {user_id_literal} "
        f"AND {p}ta.status = 'active' "
        f"AND ({p}ta.section_id IS NULL OR {p}ta.section_id = {p}sge.section_id))"
    )


def _taught_offering_exists(user_id_literal: str, offering_col: str, section_col: str) -> str:
    p = _ALIAS_PREFIX
    return (
        f"EXISTS (SELECT 1 FROM teaching_assignments {p}ta "
        f"WHERE {p}ta.teacher_user_id = {user_id_literal} "
        f"AND {p}ta.status = 'active' "
        f"AND {p}ta.grade_subject_offering_id = {offering_col} "
        f"AND ({p}ta.section_id IS NULL OR {p}ta.section_id = {section_col}))"
    )


def _taught_via_enrollment_exists(user_id_literal: str, enrollment_col: str) -> str:
    p = _ALIAS_PREFIX
    return (
        f"EXISTS (SELECT 1 FROM student_subject_enrollments {p}sse "
        f"JOIN teaching_assignments {p}ta "
        f"ON {p}ta.grade_subject_offering_id = {p}sse.grade_subject_offering_id "
        f"AND {p}ta.status = 'active' "
        f"LEFT JOIN student_grade_enrollments {p}sge ON {p}sge.id = {p}sse.grade_enrollment_id "
        f"WHERE {p}sse.id = {enrollment_col} "
        f"AND {p}ta.teacher_user_id = {user_id_literal} "
        f"AND ({p}ta.section_id IS NULL OR {p}ta.section_id = {p}sge.section_id))"
    )


def _self_predicate_sql(table: str, alias: str, user_id_literal: str) -> str:
    if table == "student_profiles":
        return f"{alias}.user_id = {user_id_literal}"
    if table in ("student_360", "quiz_attempts", "attendance_records"):
        return f"{alias}.student_id IN {_self_student_subquery(user_id_literal)}"
    if table == "student_material_progress":
        return (
            f"{alias}.student_subject_enrollment_id IN "
            "(SELECT id FROM student_subject_enrollments WHERE student_id IN "
            f"{_self_student_subquery(user_id_literal)})"
        )
    raise AssertionError(f"unhandled sensitive table {table!r}")


def _taught_predicate_sql(table: str, alias: str, user_id_literal: str) -> str:
    if table == "student_profiles":
        return f"{alias}.id IN {_taught_student_ids_subquery(user_id_literal)}"
    if table in ("student_360", "attendance_records"):
        return _taught_offering_exists(
            user_id_literal, f"{alias}.grade_subject_offering_id", f"{alias}.section_id"
        )
    if table in ("quiz_attempts", "student_material_progress"):
        return _taught_via_enrollment_exists(
            user_id_literal, f"{alias}.student_subject_enrollment_id"
        )
    raise AssertionError(f"unhandled sensitive table {table!r}")


def _row_predicate_sql(table: str, alias: str, role: str, user_id_literal: str) -> str:
    if role == "teacher":
        return _taught_predicate_sql(table, alias, user_id_literal)
    if role == "student":
        return _self_predicate_sql(table, alias, user_id_literal)
    # Any role other than "teacher"/"student" that reaches here (not "admin" — callers
    # apply institution scoping but skip this role predicate entirely for admin) has no
    # defined grant. Fail safe: no rows.
    return "FALSE"


def _institution_predicate_sql(table: str, alias: str, institution_id_literal: str) -> str:
    """Pins `alias` (a reference to `table`) to the caller's own institution. Applied for
    every role, admin included — mirrors scope_predicate()'s `institution` clause, which
    is ANDed on before the unrestricted-for-admin short-circuit, never after it.
    """
    if table in ("student_360", "student_profiles"):
        return f"{alias}.institution_id = {institution_id_literal}"
    if table in ("quiz_attempts", "attendance_records"):
        return (
            f"{alias}.student_id IN "
            f"(SELECT id FROM student_profiles WHERE institution_id = {institution_id_literal})"
        )
    if table == "student_material_progress":
        p = _ALIAS_PREFIX
        return (
            f"{alias}.student_subject_enrollment_id IN "
            f"(SELECT {p}sse.id FROM student_subject_enrollments {p}sse "
            f"JOIN student_profiles {p}sp ON {p}sp.id = {p}sse.student_id "
            f"WHERE {p}sp.institution_id = {institution_id_literal})"
        )
    raise AssertionError(f"unhandled sensitive table {table!r}")


def _apply_row_scoping(
    tree: exp.Expr, *, role: str, user_id_literal: str, institution_id_literal: str
) -> None:
    excluded_aliases = _cte_and_derived_aliases(tree)
    for select_node in tree.find_all(exp.Select):
        for alias, table in _sensitive_table_refs(select_node, excluded_aliases):
            # .where() ANDs onto any existing WHERE by default (append=True) — this can
            # only narrow what the query already asks for, never replace or OR into it.
            institution_sql = _institution_predicate_sql(table, alias, institution_id_literal)
            select_node.where(institution_sql, copy=False, dialect="postgres")
            if role == "admin":
                continue  # unrestricted beyond institution, mirrors Scope.unrestricted
            role_sql = _row_predicate_sql(table, alias, role, user_id_literal)
            select_node.where(role_sql, copy=False, dialect="postgres")


async def apply_role_scope(state: TextToSQLState) -> TextToSQLState:
    user_id = state["user_id"]
    role = state["user_role"]
    institution_id = state["institution_id"]
    sql = state["validated_sql"]
    if not sql:
        # Graph invariant: this node is only reached via validate_sql's "valid" edge,
        # which guarantees a non-empty validated_sql. Fail loudly rather than pass
        # through silently if that invariant is ever violated (e.g. direct node call).
        return {
            **state,
            "validated_sql": None,
            "error": format_error(ROLE_VIOLATION, "apply_role_scope: no validated_sql to scope"),
        }

    # validate_sql already parsed and accepted this exact string; a parse failure here
    # would mean validate_sql's own output is broken, not a role-scoping concern — let
    # that raise rather than misreport it as a ROLE_VIOLATION.
    tree: exp.Expr = sqlglot.parse_one(sql, read="postgres")

    violation = _find_blocklist_violation(tree)
    if violation is not None:
        return {
            **state,
            "validated_sql": None,
            "error": format_error(ROLE_VIOLATION, violation),
        }

    if state.get("query_source") == "template":
        return {
            **state,
            "audit_entry": {
                **(state.get("audit_entry") or {}),
                "role_scope_applied": "template_builtin",
                "scoped_by_user_id": user_id,
            },
        }

    user_id_literal = exp.Literal.string(user_id).sql(dialect="postgres")
    institution_id_literal = exp.Literal.string(institution_id).sql(dialect="postgres")
    _apply_row_scoping(
        tree,
        role=role,
        user_id_literal=user_id_literal,
        institution_id_literal=institution_id_literal,
    )

    return {
        **state,
        "validated_sql": tree.sql(dialect="postgres"),
        "audit_entry": {
            **(state.get("audit_entry") or {}),
            "role_scope_applied": "rewritten",
            "scoped_by_user_id": user_id,
        },
    }

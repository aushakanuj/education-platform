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

Table coverage (fail-closed allowlist, not a blocklist): a live investigation found that a
question routed entirely through `student_subject_enrollments`/`grade_subject_offerings`/
`subjects`/`period_grades` — none of which were in this node's original 5-table sensitive
list — returned real, unscoped, institution-wide data (a school-wide enrollment count, not
one teacher's own students) with no warning. The original design ("scope only these named
tables, everything else passes through untouched") makes every future addition to
`load_schema.REQUIRED_TABLES` exempt by default unless someone remembers to also add it
here. This is inverted: every table `validate_sql` can hand back (i.e. every name in
`REQUIRED_TABLES` other than the always-blocked `question_answer_keys`) must be classified
into exactly one of `STUDENT_SCOPED_TABLES` or `INSTITUTION_SCOPED_TABLES` below, or the
query is refused outright (`_find_unscopable_table_reference`) — a table skips scoping only
because someone deliberately, reviewably placed it on one of these two lists, never because
nobody thought to.

`STUDENT_SCOPED_TABLES` carries rows scoped to an individual student — every SELECT scope
that touches one gets the institution pin *and* the role's self/taught row predicate (a
student sees only their own rows; a teacher sees rows for the (offering, section) pairs
they teach). `INSTITUTION_SCOPED_TABLES` is institution-boundary data that isn't
individually student- or teacher-restricted by nature (a grade name, a subject list, the
institution's own row) but does still belong to exactly one institution and must not leak
across tenants — every SELECT scope that touches one gets the institution pin only, for
every role including admin.

Explicitly *not* covered by either list, and therefore refused rather than silently passed
through: the curriculum-content tables (`topics`, `subtopics`, `learning_outcomes`,
`source_materials`, `source_material_versions`, `source_chunks`, `questions`,
`question_versions`, `question_options`, `question_outcome_tags`, `common_mastery_quizzes`,
`quiz_versions`, `quiz_items`, `quiz_material_bindings`, `quiz_releases`). A live check
against this database confirmed these *are* institution-partitioned in practice (a shared
top-level curriculum is the eventual design intent per the module README, but today each
institution's `grade_subject_offerings` hangs its own `topics`, so the two seeded
institutions have disjoint topic/question sets) — but each one's institution path is a
3-to-6-hop join chain distinct per table, and reviewing all of them is real, separate work
deferred as a known, documented, lower-severity gap (curriculum content, not personal
data) rather than guessed at here. Refusing these outright is a deliberate, temporary
regression in what the assistant can answer, preferred over resurrecting the exact
silently-unscoped behavior this fix exists to close.

`query_source` branch (Step 4): a value of `"template"` skips the AST rewrite entirely (a
template's SQL already has the scoping logic — row *and* institution — hand-written into it
by its author) and just records identity in the audit entry. There is no template caller
yet — this is a clean no-op path for a future task, not dead code. The column blocklist
above still runs unconditionally regardless of this branch, per its own "applies ...
regardless of query_source" rule — a template author could still make the same mistake a
generated query could. The fail-closed table-coverage check below is likewise skipped for
templates, on the same reasoning: their scoping (or deliberate lack of it) is hand-reviewed
by the template's own author, not this node.

Self-reference sentinel (`'__CURRENT_USER_ID__'`): `STUDENT_SCOPED_TABLES` never needs
this — apply_role_scope already narrows those to the asking user's own rows silently, so
the model never has to write a self-filter for them at all. But `INSTITUTION_SCOPED_TABLES`
only gets the institution pin (deliberately — see that constant's own docstring), so a
question like "what subject do I teach" (teaching_assignments) or "what's my email"
(users) genuinely needs a `<owner column> = <the asking user>` filter that only the model
can write, and generate_sql never gives it a real identity value to use. Left
unaddressed, the model either fabricates a placeholder that matches nothing (the observed
failure: a literal like `'Your Name Here'`) or drops the self-filter entirely, over-
returning institution-wide data. generate_sql's prompt instead teaches one fixed, literal
token; `_resolve_current_user_sentinel` finds and replaces it with the real
`state["user_id"]` here, before any row/institution scoping runs — the same node, and
the same identity-sourcing discipline (state only, never the question or model output),
already used for every other identity-keyed predicate in this file. This runs for every
role, not just teacher/student: nothing about self-reference is role-specific, and this
node is not the layer that decides whether a role should be allowed to ask about itself.

If the model needs self-reference but doesn't use the token — a still-fabricated literal,
or a subquery guessing at identity — this is deliberately *not* caught by a dedicated
rejection or pattern-matching check here. Any such check would be pattern-matching an
open-ended set of possible fabrications (the model could invent any string, not just the
one literal observed so far), which is exactly the kind of fragile, easily-incomplete text
heuristic this pipeline already avoids leaning on (see sanity_check.py's own two
heuristic checks, each explicitly labeled as a guess, never a certainty). The residual
failure mode is also a data-quality problem, not a security one: apply_role_scope's own
institution/row predicates below are ANDed on regardless of what the model's own WHERE
clause says, so a still-wrong self-reference can only ever produce a wrong *answer*
(most often an empty one), never a widened one — and sanity_check's existing
`zero_rows`/`zero_valued_aggregate` checks already catch that exact symptom and downgrade
confidence accordingly, with no new mechanism needed.
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
# scope (outer query, CTE, or nested subquery) that touches one of these gets the
# institution pin *and* a self/taught row predicate ANDed on, keyed off
# state["user_id"]/state["user_role"]. Named and reviewable here rather than inferred
# from, say, "has a student_id column" at runtime.
STUDENT_SCOPED_TABLES: Final[frozenset[str]] = frozenset(
    {
        "student_360",
        "student_profiles",
        "quiz_attempts",
        "attendance_records",
        "student_material_progress",
        "student_subject_enrollments",
        "student_grade_enrollments",
        "attempt_answers",
    }
)

# Tables that belong to exactly one institution but aren't individually student- or
# teacher-restricted by nature (a grade's name, a subject list, the institution's own
# row) — every SELECT scope that touches one of these gets the institution pin only, for
# every role including admin. See the module docstring's "Table coverage" section for why
# this list exists (as the allowlist half of a fail-closed inversion) and why the
# curriculum-content tables below are deliberately on neither list yet.
INSTITUTION_SCOPED_TABLES: Final[frozenset[str]] = frozenset(
    {
        "institutions",
        "users",
        "user_roles",
        "refresh_sessions",
        "grades",
        "subjects",
        "academic_periods",
        "period_grades",
        "sections",
        "grade_subject_offerings",
        "teaching_assignments",
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


# The fixed, literal self-reference token generate_sql's prompt teaches the model to
# write verbatim whenever a question needs to compare a column against the asking
# user's own identity (e.g. `teacher_user_id = '__CURRENT_USER_ID__'`) — see
# generate_sql.py's own docstring/system prompt for why this exists. An ordinary string
# literal, not SQL bind-parameter syntax (`:name`): validate_sql and sqlglot need no
# special-casing to accept it, it round-trips through ordinary parsing exactly like any
# other string value the model might have written, and it's resolved here — the one
# place in this pipeline that already builds every other identity-keyed literal from
# state["user_id"] — via the same find-then-replace mechanism `_apply_row_scoping` uses
# for its own injected predicates.
_CURRENT_USER_SENTINEL: Final[str] = "__CURRENT_USER_ID__"


def _resolve_current_user_sentinel(tree: exp.Expr, user_id: str) -> None:
    # Materialize the matching literal nodes to a list *before* replacing any of them:
    # `find_all` is a live traversal, and `Literal.replace()` swaps a node in place —
    # exactly the mutate-while-iterating hazard `_apply_row_scoping`'s own docstring
    # warns about, here on exp.Literal instead of exp.Select.
    targets = [
        literal
        for literal in tree.find_all(exp.Literal)
        if literal.is_string and literal.this == _CURRENT_USER_SENTINEL
    ]
    for literal in targets:
        literal.replace(exp.Literal.string(user_id))


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


def _scoped_table_refs(
    select_node: exp.Select, excluded_aliases: set[str]
) -> list[tuple[str, str]]:
    """(alias-or-name, canonical table name) for each table this select scope directly
    references that is on `STUDENT_SCOPED_TABLES` or `INSTITUTION_SCOPED_TABLES`. Which of
    the two a name belongs to is re-derived by the caller (`_apply_row_scoping`) rather
    than tagged here, since the two tiers dispatch to different predicate builders below.
    """
    refs: list[tuple[str, str]] = []
    for table_node in _direct_tables(select_node):
        name = table_node.name
        if name.lower() in excluded_aliases:
            continue  # a reference to a CTE/derived table by name, not a real table
        if name.lower() not in STUDENT_SCOPED_TABLES and name.lower() not in (
            INSTITUTION_SCOPED_TABLES
        ):
            continue
        alias = table_node.alias or table_node.name
        refs.append((alias, name.lower()))
    return refs


def _find_unscopable_table_reference(tree: exp.Expr, excluded_aliases: set[str]) -> str | None:
    """A table this query directly references that is on neither `STUDENT_SCOPED_TABLES`
    nor `INSTITUTION_SCOPED_TABLES` — i.e. one `validate_sql` allowed through (it's in
    `load_schema.REQUIRED_TABLES`) but that nobody has yet reviewed and classified for
    role-based scoping here. Fail closed: refuse the query rather than let it pass through
    unscoped, which is exactly the gap this rewrite exists to close. See the module
    docstring's "Table coverage" section for the current list of deferred tables this
    surfaces for (curriculum content, not personal data).
    """
    for select_node in tree.find_all(exp.Select):
        for table_node in _direct_tables(select_node):
            name = table_node.name.lower()
            if name in excluded_aliases:
                continue
            if name in STUDENT_SCOPED_TABLES or name in INSTITUTION_SCOPED_TABLES:
                continue
            return (
                f"table `{table_node.name}` is not yet reviewed for role-based scoping "
                "and cannot be queried by the text-to-SQL assistant"
            )
    return None


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


def _taught_period_grade_exists(
    user_id_literal: str, period_grade_col: str, section_col: str
) -> str:
    """A teacher "teaches" a `student_grade_enrollments` row if any of their teaching
    assignments' offering belongs to that row's `period_grade_id` — one level up from
    `_taught_offering_exists`, which matches a specific offering rather than the grade as
    a whole, since `student_grade_enrollments` predates subject enrollment. This is
    deliberately coarser than the subject-level tables: `student_grade_enrollments` has
    no subject dimension of its own, so an all-sections (`section_id IS NULL`) grant for
    *any* subject taught in that grade correctly reaches every student's grade-level row
    in that grade — not only the students of that one subject.
    """
    p = _ALIAS_PREFIX
    return (
        f"EXISTS (SELECT 1 FROM teaching_assignments {p}ta "
        f"JOIN grade_subject_offerings {p}gso ON {p}gso.id = {p}ta.grade_subject_offering_id "
        f"WHERE {p}ta.teacher_user_id = {user_id_literal} "
        f"AND {p}ta.status = 'active' "
        f"AND {p}gso.period_grade_id = {period_grade_col} "
        f"AND ({p}ta.section_id IS NULL OR {p}ta.section_id = {section_col}))"
    )


def _self_predicate_sql(table: str, alias: str, user_id_literal: str) -> str:
    if table == "student_profiles":
        return f"{alias}.user_id = {user_id_literal}"
    if table in (
        "student_360",
        "quiz_attempts",
        "attendance_records",
        "student_subject_enrollments",
        "student_grade_enrollments",
    ):
        return f"{alias}.student_id IN {_self_student_subquery(user_id_literal)}"
    if table == "student_material_progress":
        return (
            f"{alias}.student_subject_enrollment_id IN "
            "(SELECT id FROM student_subject_enrollments WHERE student_id IN "
            f"{_self_student_subquery(user_id_literal)})"
        )
    if table == "attempt_answers":
        return (
            f"{alias}.attempt_id IN (SELECT id FROM quiz_attempts WHERE student_id IN "
            f"{_self_student_subquery(user_id_literal)})"
        )
    raise AssertionError(f"unhandled sensitive table {table!r}")


def _taught_predicate_sql(table: str, alias: str, user_id_literal: str) -> str:
    p = _ALIAS_PREFIX
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
    if table == "student_subject_enrollments":
        section_subquery = (
            f"(SELECT {p}sge.section_id FROM student_grade_enrollments {p}sge "
            f"WHERE {p}sge.id = {alias}.grade_enrollment_id)"
        )
        return _taught_offering_exists(
            user_id_literal, f"{alias}.grade_subject_offering_id", section_subquery
        )
    if table == "student_grade_enrollments":
        return _taught_period_grade_exists(
            user_id_literal, f"{alias}.period_grade_id", f"{alias}.section_id"
        )
    if table == "attempt_answers":
        enrollment_subquery = (
            f"(SELECT {p}qa.student_subject_enrollment_id FROM quiz_attempts {p}qa "
            f"WHERE {p}qa.id = {alias}.attempt_id)"
        )
        return _taught_via_enrollment_exists(user_id_literal, enrollment_subquery)
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
    is ANDed on before the unrestricted-for-admin short-circuit, never after it. Covers
    both `STUDENT_SCOPED_TABLES` (paired with a self/taught row predicate) and
    `INSTITUTION_SCOPED_TABLES` (this predicate alone).
    """
    p = _ALIAS_PREFIX
    if table in ("student_360", "student_profiles"):
        return f"{alias}.institution_id = {institution_id_literal}"
    if table in (
        "quiz_attempts",
        "attendance_records",
        "student_subject_enrollments",
        "student_grade_enrollments",
    ):
        return (
            f"{alias}.student_id IN "
            f"(SELECT id FROM student_profiles WHERE institution_id = {institution_id_literal})"
        )
    if table == "student_material_progress":
        return (
            f"{alias}.student_subject_enrollment_id IN "
            f"(SELECT {p}sse.id FROM student_subject_enrollments {p}sse "
            f"JOIN student_profiles {p}sp ON {p}sp.id = {p}sse.student_id "
            f"WHERE {p}sp.institution_id = {institution_id_literal})"
        )
    if table == "attempt_answers":
        return (
            f"{alias}.attempt_id IN (SELECT {p}qa.id FROM quiz_attempts {p}qa "
            f"WHERE {p}qa.student_id IN "
            f"(SELECT id FROM student_profiles WHERE institution_id = {institution_id_literal}))"
        )
    if table == "institutions":
        return f"{alias}.id = {institution_id_literal}"
    if table == "users":
        return f"{alias}.institution_id = {institution_id_literal}"
    if table in ("user_roles", "refresh_sessions"):
        return (
            f"{alias}.user_id IN "
            f"(SELECT id FROM users WHERE institution_id = {institution_id_literal})"
        )
    if table in ("grades", "subjects", "academic_periods"):
        return f"{alias}.institution_id = {institution_id_literal}"
    if table == "period_grades":
        return (
            f"{alias}.academic_period_id IN "
            f"(SELECT id FROM academic_periods WHERE institution_id = {institution_id_literal})"
        )
    if table in ("sections", "grade_subject_offerings"):
        return (
            f"{alias}.period_grade_id IN "
            f"(SELECT {p}pg.id FROM period_grades {p}pg "
            f"JOIN academic_periods {p}ap ON {p}ap.id = {p}pg.academic_period_id "
            f"WHERE {p}ap.institution_id = {institution_id_literal})"
        )
    if table == "teaching_assignments":
        return (
            f"{alias}.academic_period_id IN "
            f"(SELECT id FROM academic_periods WHERE institution_id = {institution_id_literal})"
        )
    raise AssertionError(f"unhandled scoped table {table!r}")


def _apply_row_scoping(
    tree: exp.Expr,
    *,
    excluded_aliases: set[str],
    role: str,
    user_id_literal: str,
    institution_id_literal: str,
) -> None:
    # Materialize the select scopes (and each one's scoped-table refs) to a plain list
    # *before* mutating anything: `.where()` below parses and splices in a new subquery,
    # which is itself an exp.Select containing further scoped-table references (an
    # INSTITUTION_SCOPED_TABLES predicate can reference another INSTITUTION_SCOPED_TABLES
    # table, e.g. grade_subject_offerings -> period_grades -> academic_periods). Since
    # `find_all` is a live traversal of the tree, iterating it directly here would walk
    # into those newly-injected subqueries too and try to scope them all over again —
    # each pass injecting another nested subquery for `find_all` to discover, which never
    # terminates. Injected subqueries are this function's own, already-correct-by-
    # construction SQL; they must never be re-scanned by the mechanism that wrote them.
    work = [
        (select_node, refs)
        for select_node in tree.find_all(exp.Select)
        if (refs := _scoped_table_refs(select_node, excluded_aliases))
    ]
    for select_node, refs in work:
        for alias, table in refs:
            # .where() ANDs onto any existing WHERE by default (append=True) — this can
            # only narrow what the query already asks for, never replace or OR into it.
            institution_sql = _institution_predicate_sql(table, alias, institution_id_literal)
            select_node.where(institution_sql, copy=False, dialect="postgres")
            if table not in STUDENT_SCOPED_TABLES:
                continue  # INSTITUTION_SCOPED_TABLES gets the institution pin only
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

    _resolve_current_user_sentinel(tree, user_id)

    excluded_aliases = _cte_and_derived_aliases(tree)
    unscopable = _find_unscopable_table_reference(tree, excluded_aliases)
    if unscopable is not None:
        return {
            **state,
            "validated_sql": None,
            "error": format_error(ROLE_VIOLATION, unscopable),
        }

    user_id_literal = exp.Literal.string(user_id).sql(dialect="postgres")
    institution_id_literal = exp.Literal.string(institution_id).sql(dialect="postgres")
    _apply_row_scoping(
        tree,
        excluded_aliases=excluded_aliases,
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

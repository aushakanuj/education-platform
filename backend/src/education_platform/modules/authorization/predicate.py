"""Turn a resolved `Scope` into a SQL filter, for any query that can name the right columns.

Separating this from `insights.service` exists for one reason: **the rules should be
written once and the plumbing many times.**

There are two halves to applying a permission boundary, and only one of them is
table-specific:

* **The facts** -- who this principal is, which institution, which (offering, section)
  pairs they teach, whether they have a student record of their own. That is `Scope`, and
  it is the same answer whichever table you are reading.
* **The filter** -- the SQL that expresses those facts against the columns actually in
  front of you. `student_360` has `institution_id` on the row; `attendance_records` does
  not have that column at all and must reach it through a join.

The original `scope_predicate` fused the two, hard-coding `student_360`. That worked while
every governed read went through the register, and stopped working the moment a
text-to-SQL pipeline needed the same rules over `attendance_records`, `quiz_attempts` and
the rest. The response to that must not be a second implementation of the rules: the two
would drift, and a fix applied to one would silently never reach the other. This project
has already paid for that twice -- see `docs/design/02` §11a.2 and commit `b895828`.

So: `ScopeColumns` says *which columns in your query carry these concepts*, and
`scope_predicate_for` writes the same rules against them.

**What this cannot defend against, stated plainly so nobody assumes otherwise:**

1. **A wrong column mapping.** Nothing here can tell that you passed the *right*
   `institution_id`; swap two columns and the boundary is silently nonsense. This is the
   real residual risk of the design, and the only honest mitigation is a test per caller
   that runs a known principal against known data and asserts the row count -- see
   `tests/test_insights_api.py` for the shape.
2. **Forgetting to apply it at all.** A predicate that is built and never put in the
   `WHERE` clause protects nothing, and no amount of care here changes that.
3. Both of the above have the same real answer if this ever goes past a POC: enforce the
   boundary **in the database**, with row-level security policies or a role granted
   `SELECT` on nothing but the permitted rows. Then a query that forgets the filter
   returns nothing instead of everything, and the application layer stops being the last
   line. Recorded in `docs/design/02` §11b.7.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, and_, false, or_, tuple_
from sqlalchemy.dialects import postgresql

from education_platform.modules.authorization.scope import Scope


@dataclass(frozen=True, slots=True)
class ScopeColumns:
    """Which columns of *your* query carry the concepts the boundary reasons about.

    Any SQLAlchemy column expression will do, including one from a joined table or an
    aliased subquery -- these are not required to live on a single table, because for most
    tables they do not. `attendance_records` reaches `institution_id` only through the
    student or the offering.

    All four are required. There is no "close enough" subset: leaving out
    `institution_id` is how an administrator ends up reading another school, and leaving
    out `section_id` is how a Grade 8 teacher ends up reading Grade 9.
    """

    institution_id: ColumnElement[Any]
    student_id: ColumnElement[Any]
    grade_subject_offering_id: ColumnElement[Any]
    section_id: ColumnElement[Any]


def _taught_predicate(scope: Scope, columns: ScopeColumns) -> ColumnElement[bool] | None:
    """Rows for the exact (offering, section) pairs the principal teaches.

    An assignment naming no section covers every section of that offering. One that names a
    section matches only that section -- a row whose `section_id` is NULL (a student
    enrolled in a grade but not placed in a section) therefore does not match, which is the
    safe direction to fail.
    """
    if not scope.taught_offering_sections:
        return None

    whole_offerings = sorted(
        (offering for offering, section in scope.taught_offering_sections if section is None),
        key=str,
    )
    exact_pairs = sorted(
        ((o, s) for o, s in scope.taught_offering_sections if s is not None),
        key=lambda pair: (str(pair[0]), str(pair[1])),
    )

    clauses: list[ColumnElement[bool]] = []
    if whole_offerings:
        clauses.append(columns.grade_subject_offering_id.in_(whole_offerings))
    if exact_pairs:
        clauses.append(
            tuple_(columns.grade_subject_offering_id, columns.section_id).in_(exact_pairs)
        )
    return clauses[0] if len(clauses) == 1 else or_(*clauses)


def scope_predicate_for(scope: Scope, columns: ScopeColumns) -> ColumnElement[bool]:
    """The permission boundary, written against whichever columns you supply.

    Institution is **always** pinned, administrators included: `unrestricted` means the
    whole school, never every school on the server. Beyond that, a principal reaches a row
    by exactly one of two routes:

    * it is their own student record -- every subject of it, and
    * it belongs to an (offering, section) pair they teach.

    Filtering on the student list alone is not enough: a Grade 8 Mathematics teacher
    reaches those pupils, but each pupil also has Science and English rows, and a student
    filter lets all of them through. The boundary has to match the grain of the data.

    A principal who can reach nothing compiles to `false` -- an empty result set,
    deliberately not an error, because an error would confirm the data exists.
    """
    institution = columns.institution_id == scope.institution_id
    if scope.unrestricted:
        return institution

    grants: list[ColumnElement[bool]] = []
    if scope.self_student_id is not None:
        grants.append(columns.student_id == scope.self_student_id)
    taught = _taught_predicate(scope, columns)
    if taught is not None:
        grants.append(taught)

    if not grants:
        return false()
    return and_(institution, grants[0] if len(grants) == 1 else or_(*grants))


def _assert_inlinable(scope: Scope) -> None:
    """Refuse to inline anything that is not a UUID we produced.

    `scope_sql` writes values straight into SQL text, so this is the one place where a
    value's *type* is load-bearing. Today every `Scope` comes from `scope_for()` reading
    our own database, so they are all UUIDs -- but nothing in the type system stops a
    future caller building one from a request parameter, and at that moment inlining
    becomes SQL injection. Checking is nearly free; discovering it later is not.
    """
    values: list[object] = [scope.institution_id, scope.self_student_id]
    for offering, section in scope.taught_offering_sections:
        values.extend((offering, section))

    for value in values:
        if value is not None and not isinstance(value, UUID):
            raise TypeError(
                "scope_sql inlines values into SQL and will only inline UUIDs; "
                f"got {type(value).__name__}. Build the Scope from the database, "
                "never from request input."
            )


def scope_sql(scope: Scope, columns: ScopeColumns) -> str:
    """The same predicate rendered as PostgreSQL text, for pipelines that build SQL strings.

    For callers that assemble SQL as text rather than as SQLAlchemy objects -- a
    text-to-SQL pipeline, most obviously -- so they can hold the boundary without either a
    database session or a second implementation of the rules.

    **The result is always parenthesised, and that is not cosmetic.** The predicate's own
    top level is an `AND`, and `AND` binds tighter than `OR`. An unwrapped fragment pasted
    into a larger clause as ``WHERE <fragment> OR something`` parses as
    ``(boundary) OR (something)`` -- which is true for every row in the table, so the
    boundary disappears entirely. Wrapping makes the fragment safe to compose in any
    position, including one the caller did not think about.

    Values are inlined (`literal_binds`) because a fragment has nowhere to bind parameters.
    `_assert_inlinable` keeps that safe by refusing anything that is not a UUID.

    Do not cache the result. A rendered fragment is one principal's boundary, and reusing
    it for a different request hands that principal's reach to somebody else.
    """
    _assert_inlinable(scope)
    # SQLAlchemy ships no annotation for `dialect()`, so mypy calls this untyped.
    dialect: Any = postgresql.dialect()  # type: ignore[no-untyped-call]
    rendered = str(
        scope_predicate_for(scope, columns).compile(
            dialect=dialect,
            compile_kwargs={"literal_binds": True},
        )
    )
    return f"({rendered})"

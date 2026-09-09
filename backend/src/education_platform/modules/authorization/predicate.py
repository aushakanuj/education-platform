"""Turn a resolved `Scope` into a SQL filter via caller-supplied column mapping.

Rules live here once; each query supplies its own `ScopeColumns`. Wrong mapping is silent —
see `docs/design/02` §11. `scope_sql` must stay parenthesised and UUID-only (§11b.7 for RLS).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, and_, false, or_, tuple_
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import InstrumentedAttribute

from education_platform.modules.authorization.scope import Scope

ColumnLike = ColumnElement[Any] | InstrumentedAttribute[Any]


@dataclass(frozen=True, slots=True)
class ScopeColumns:
    """Which query columns carry institution, student, offering, and section."""

    institution_id: ColumnLike
    student_id: ColumnLike
    grade_subject_offering_id: ColumnLike
    section_id: ColumnLike


def _taught_predicate(scope: Scope, columns: ScopeColumns) -> ColumnElement[bool] | None:
    """Match exact (offering, section) pairs the principal teaches."""
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
    """Institution-pinned boundary: own student rows or taught (offering, section) pairs."""
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
    """Refuse non-UUID values before inlining into SQL text."""
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
    """Same predicate as PostgreSQL text; always parenthesised, UUID literals only."""
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

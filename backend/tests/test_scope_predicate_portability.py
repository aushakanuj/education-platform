"""The boundary must mean the same thing wherever it is applied.

Written in response to a review of the text-to-SQL scoping work, which raised two things:
a second implementation of "which students belong to this teacher" will drift from the
first, and nothing today would catch it; and an administrator treated as unrestricted
without an institution filter is a cross-tenant leak waiting to happen.

Both are fair. The answer to the first is not "please remember to keep them in step" --
it is to make one set of rules usable from more than one place, and then to prove that the
renderings agree. `authorization.predicate` holds the rules; this file holds the proof.

The scenarios below are the ones the review asked for: a teacher assigned to one section,
a teacher assigned to a whole offering (`section_id IS NULL`), and a principal who can
reach nothing at all.
"""

from __future__ import annotations

from dataclasses import fields
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Column, MetaData, Table, Uuid

from education_platform.modules.authorization.predicate import (
    ScopeColumns,
    scope_predicate_for,
    scope_sql,
)
from education_platform.modules.authorization.scope import Scope
from education_platform.modules.insights.service import STUDENT_360_COLUMNS, scope_predicate

INSTITUTION = UUID("11111111-1111-1111-1111-111111111111")
OTHER_INSTITUTION = UUID("99999999-9999-9999-9999-999999999999")
OFFERING = UUID("22222222-2222-2222-2222-222222222222")
SECTION = UUID("33333333-3333-3333-3333-333333333333")
STUDENT = UUID("44444444-4444-4444-4444-444444444444")

#: Stands in for whatever table a caller is actually querying -- an attendance join, a
#: text-to-SQL subquery. Deliberately *not* student_360, and deliberately with different
#: column names, because that is the whole point: the rules travel, the column names do not.
other_table = Table(
    "some_other_query",
    MetaData(),
    Column("tenant", Uuid(as_uuid=True)),
    Column("pupil", Uuid(as_uuid=True)),
    Column("offering", Uuid(as_uuid=True)),
    Column("klass", Uuid(as_uuid=True)),
)

OTHER_COLUMNS = ScopeColumns(
    institution_id=other_table.c.tenant,
    student_id=other_table.c.pupil,
    grade_subject_offering_id=other_table.c.offering,
    section_id=other_table.c.klass,
)


def _scope(**over: object) -> Scope:
    base: dict[str, object] = {
        "institution_id": INSTITUTION,
        "roles": frozenset({"teacher"}),
        "unrestricted": False,
        "taught_offering_sections": frozenset(),
        "enrolled_offering_sections": frozenset(),
        "student_ids": frozenset(),
        "self_student_id": None,
    }
    base.update(over)
    return Scope(**base)  # type: ignore[arg-type]


SCENARIOS = {
    "administrator": _scope(roles=frozenset({"administrator"}), unrestricted=True),
    "teacher-with-section": _scope(taught_offering_sections=frozenset({(OFFERING, SECTION)})),
    "teacher-whole-offering": _scope(taught_offering_sections=frozenset({(OFFERING, None)})),
    "student": _scope(roles=frozenset({"student"}), self_student_id=STUDENT),
    "teacher-who-is-also-a-pupil": _scope(
        roles=frozenset({"teacher", "student"}),
        taught_offering_sections=frozenset({(OFFERING, SECTION)}),
        self_student_id=STUDENT,
    ),
    "reaches-nothing": _scope(),
}


def _sql(scope: Scope, columns: ScopeColumns) -> str:
    return scope_sql(scope, columns)


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_the_register_binding_matches_the_generic_rules(name: str) -> None:
    """`insights.scope_predicate` must be the generic rules and nothing more.

    If someone edits the wrapper into having its own opinion, this fails.
    """
    scope = SCENARIOS[name]
    bound = str(scope_predicate(scope))
    generic = str(scope_predicate_for(scope, STUDENT_360_COLUMNS))
    assert bound == generic


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_the_same_rules_survive_being_applied_to_a_different_table(name: str) -> None:
    """Rendered against other columns, the *shape* of the boundary is unchanged.

    Compared with the column names normalised away: what must match is which concepts are
    constrained and how they are combined, not what the columns happen to be called.
    """
    scope = SCENARIOS[name]
    register = _sql(scope, STUDENT_360_COLUMNS)
    elsewhere = _sql(scope, OTHER_COLUMNS)

    normalised = (
        elsewhere.replace("some_other_query.tenant", "student_360.institution_id")
        .replace("some_other_query.pupil", "student_360.student_id")
        .replace("some_other_query.offering", "student_360.grade_subject_offering_id")
        .replace("some_other_query.klass", "student_360.section_id")
    )
    assert normalised == register


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_every_scope_pins_the_institution_or_matches_nothing(name: str) -> None:
    """Rule 6, as a property rather than an example.

    The only acceptable alternatives are "filtered to my institution" and "no rows at all".
    An administrator is *not* exempt: `unrestricted` means the whole school, never every
    school. This is the exact assumption the review flagged, and the exact bug fixed in
    `b895828` -- asserted here so no future edit can quietly reintroduce it.
    """
    rendered = _sql(SCENARIOS[name], STUDENT_360_COLUMNS)
    if rendered.strip().lower() == "(false)":
        return
    assert f"institution_id = '{INSTITUTION}'" in rendered


def test_an_administrator_is_still_bounded_by_their_own_institution() -> None:
    """The single most load-bearing line in the file, spelled out."""
    admin = SCENARIOS["administrator"]
    rendered = _sql(admin, STUDENT_360_COLUMNS)

    assert f"'{INSTITUTION}'" in rendered
    assert str(OTHER_INSTITUTION) not in rendered
    assert rendered.strip() == f"(student_360.institution_id = '{INSTITUTION}')"


def test_a_principal_who_reaches_nothing_compiles_to_false_not_to_everything() -> None:
    """A boundary that fails open is worse than one that fails loudly."""
    assert _sql(SCENARIOS["reaches-nothing"], STUDENT_360_COLUMNS).strip().lower() == "(false)"


# ------------------------------------------------------------------ composition safety


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_the_fragment_is_parenthesised_so_it_cannot_be_or_ed_away(name: str) -> None:
    """The bypass this file exists to prevent, and it was real.

    The predicate's own top level is an `AND`, and `AND` binds tighter than `OR`. An
    unwrapped fragment pasted as ``WHERE <fragment> OR x`` parses as
    ``(boundary) OR (x)`` -- true for every row, boundary gone. Wrapping is what makes the
    fragment safe to compose in a position the caller did not think about.
    """
    rendered = _sql(SCENARIOS[name], STUDENT_360_COLUMNS)
    assert rendered.startswith("(") and rendered.endswith(")")


def _is_one_balanced_group(sql: str) -> bool:
    """Whether the whole string is a *single* parenthesised group.

    This is the property that makes composition safe, and it is stronger than "starts with
    ( and ends with )": `(a) AND (b)` satisfies that and is still splittable by a
    surrounding `OR`. The check is that the opening parenthesis does not close until the
    very last character, so there is no top-level operator outside the group for `OR` to
    bind to.

    Safe to do by counting here because every literal we inline is a UUID, and a UUID
    contains no parentheses. Do not reuse this on arbitrary SQL.
    """
    if not (sql.startswith("(") and sql.endswith(")")):
        return False
    depth = 0
    for index, char in enumerate(sql):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0 and index != len(sql) - 1:
                return False
    return depth == 0


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_the_fragment_is_one_group_so_no_surrounding_or_can_split_it(name: str) -> None:
    """The real proof that the bypass is closed, for every scope shape.

    Deliberately not written with a SQL parser. sqlglot is present in this machine's
    virtualenv as a leftover but is *not* in the lockfile, so an `importorskip` version of
    this test would pass locally and silently skip in CI -- which is how a security test
    quietly stops existing.
    """
    assert _is_one_balanced_group(_sql(SCENARIOS[name], STUDENT_360_COLUMNS))


def test_the_group_check_would_actually_catch_the_old_bug() -> None:
    """A test of the test. An unwrapped fragment must fail the check above."""
    unwrapped = "student_360.institution_id = 'x' AND (a, b) IN (('c', 'd'))"
    assert not _is_one_balanced_group(unwrapped)
    assert not _is_one_balanced_group(f"({unwrapped[:20]}) AND ({unwrapped[20:]})")
    assert _is_one_balanced_group(f"({unwrapped})")


# ------------------------------------------------------------ inlining is type-checked


def test_a_non_uuid_value_is_refused_rather_than_inlined() -> None:
    """`scope_sql` writes values into SQL text, so their type is load-bearing.

    Nothing in the type system stops a future caller building a Scope from a request
    parameter. At that moment inlining becomes injection, so the check lives here.
    """
    hostile = _scope(institution_id="' OR '1'='1")
    with pytest.raises(TypeError, match="only inline UUIDs"):
        scope_sql(hostile, STUDENT_360_COLUMNS)


def test_a_non_uuid_hidden_inside_a_taught_pair_is_also_refused() -> None:
    """The obvious field is checked; so is the one buried in a frozenset of tuples."""
    hostile = _scope(taught_offering_sections=frozenset({("' OR 1=1 --", SECTION)}))
    with pytest.raises(TypeError, match="only inline UUIDs"):
        scope_sql(hostile, STUDENT_360_COLUMNS)


def test_the_sqlalchemy_path_is_unaffected_by_the_inlining_check() -> None:
    """Bind parameters make the type question moot, so that path stays usable."""
    odd = _scope(institution_id="not-a-uuid")
    assert scope_predicate_for(odd, STUDENT_360_COLUMNS) is not None


# ------------------------------------------------------------------------- tripwire


def test_the_predicate_knows_about_every_field_on_scope() -> None:
    """Fails deliberately when somebody adds a grant to `Scope`.

    The dangerous version of this change is silent: a new field is added for a new kind of
    principal, the predicate never learns about it, and the boundary is quietly wrong in
    whichever direction the omission happens to fall. This test cannot know the right
    answer -- it just refuses to let the decision be skipped.

    If you are here because this failed: decide whether the new field grants access,
    handle it in `scope_predicate_for` if so, then add it below.
    """
    considered = {
        # Used by the predicate.
        "institution_id",
        "unrestricted",
        "taught_offering_sections",
        "self_student_id",
        # Deliberately not used, and each for a reason worth remembering.
        "roles",  # capability checks, not row filtering
        "enrolled_offering_sections",  # grants nothing; self_student_id already covers it
        "student_ids",  # coarser than a row boundary; see Scope.allows_student
    }
    actual = {field.name for field in fields(Scope)}
    assert actual == considered, (
        "Scope's fields changed. Decide whether the difference grants access to rows, "
        "handle it in scope_predicate_for, and update this list."
    )


def test_the_rendered_sql_needs_no_database_session() -> None:
    """What makes reuse possible for a pipeline that only builds strings.

    Every value inlined comes from a Scope resolved out of our own database -- UUIDs, never
    user text -- so inlining is safe here. The test exists to keep that property visible.
    """
    rendered = _sql(SCENARIOS["teacher-with-section"], OTHER_COLUMNS)
    assert ":" not in rendered, "no unbound parameters may survive into the fragment"
    assert str(OFFERING) in rendered
    assert str(SECTION) in rendered


def test_a_whole_offering_assignment_does_not_narrow_to_one_section() -> None:
    """`section_id IS NULL` on an assignment means every section of that offering."""
    rendered = _sql(SCENARIOS["teacher-whole-offering"], STUDENT_360_COLUMNS)
    assert str(OFFERING) in rendered
    assert str(SECTION) not in rendered


def test_a_teacher_who_is_also_a_pupil_gets_both_routes_not_one() -> None:
    """Their own record *and* what they teach. Losing either is a real defect."""
    rendered = _sql(SCENARIOS["teacher-who-is-also-a-pupil"], STUDENT_360_COLUMNS)
    assert str(STUDENT) in rendered, "their own record must still be reachable"
    assert str(OFFERING) in rendered, "what they teach must still be reachable"
    assert " OR " in rendered.upper()


def test_scope_columns_cannot_be_partially_supplied() -> None:
    """Omitting institution_id is how the cross-tenant bug happens; make it impossible."""
    with pytest.raises(TypeError):
        ScopeColumns(  # type: ignore[call-arg]
            institution_id=other_table.c.tenant,
            student_id=other_table.c.pupil,
        )


def test_scope_columns_accepts_columns_from_more_than_one_table() -> None:
    """The realistic case: `attendance_records` has no institution_id of its own.

    Any query needing this boundary will reach institution through a join, so the mapping
    has to accept expressions from wherever they come from -- otherwise the only reusable
    table is the one we already had.
    """
    joined = Table("students", MetaData(), Column("institution_id", Uuid(as_uuid=True)))
    mixed = ScopeColumns(
        institution_id=joined.c.institution_id,
        student_id=other_table.c.pupil,
        grade_subject_offering_id=other_table.c.offering,
        section_id=other_table.c.klass,
    )
    rendered = scope_sql(SCENARIOS["teacher-with-section"], mixed)
    assert "students.institution_id" in rendered
    assert "some_other_query.offering" in rendered


def test_scope_values_are_read_from_the_scope_not_hardcoded() -> None:
    """Guards against a copy-paste that pins the wrong tenant for everyone."""
    other = _scope(institution_id=OTHER_INSTITUTION, unrestricted=True)
    rendered = scope_sql(other, STUDENT_360_COLUMNS)
    assert str(OTHER_INSTITUTION) in rendered
    assert str(INSTITUTION) not in rendered


def test_an_unknown_scope_shape_does_not_silently_widen() -> None:
    """A student with no enrolments and no teaching reaches nothing, not everything."""
    lonely = _scope(roles=frozenset({"student"}), self_student_id=uuid4())
    rendered = scope_sql(lonely, STUDENT_360_COLUMNS)
    assert f"institution_id = '{INSTITUTION}'" in rendered
    assert "student_id" in rendered

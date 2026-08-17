"""Ask-the-data: the guardrail, and the boundary holding through the HTTP layer.

Split deliberately. The guardrail tests are pure functions over SQL text and run in
milliseconds, so every hostile case worth thinking of is cheap to add. The endpoint tests
go through HTTP against a real school, because Stage 1 taught that a green unit suite says
nothing about whether the route works.

No test reaches OpenRouter. The model is an injected callable, so what is under test is the
platform's behaviour given some SQL -- including SQL no model would ever write, which is
exactly the SQL a guardrail exists for.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from education_platform.db.url import to_sync_url
from education_platform.modules.authorization.scope import Scope
from education_platform.modules.nl_query import service
from education_platform.modules.nl_query.guardrail import GuardrailViolation, guard
from education_platform.modules.synthetic.generator import SchoolSpec, generate_school

TEST_SPEC = SchoolSpec(sections_per_grade=2, students_per_section=3, term_weeks=2)
SCHOOL = TEST_SPEC.institution_name
PASSWORD = "demo1234"

ADMIN = "fatima.almansouri@alnoor.school"
TEACHER = "meera.krishnan@alnoor.school"
STUDENT = "student25@alnoor.school"

LIST_EVERYTHING = "SELECT full_name, subject, mastery_percent FROM student_360"


def _open_scope() -> Scope:
    """An administrator-shaped scope — the widest the guardrail will ever be handed."""
    return Scope(
        institution_id=uuid4(),
        roles=frozenset({"administrator"}),
        unrestricted=True,
        taught_offering_sections=frozenset(),
        enrolled_offering_sections=frozenset(),
        student_ids=frozenset(),
        self_student_id=None,
    )


# ------------------------------------------------------------------ guardrail


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM student_360",
        "UPDATE student_360 SET mastery_percent = 100",
        "DROP VIEW student_360",
        "INSERT INTO student_360 VALUES (1)",
        "CREATE TABLE evil (id int)",
        "ALTER VIEW student_360 RENAME TO gone",
    ],
    ids=["delete", "update", "drop", "insert", "create", "alter"],
)
def test_anything_that_is_not_a_select_is_refused(sql: str) -> None:
    with pytest.raises(GuardrailViolation):
        guard(sql, _open_scope())


def test_a_second_statement_smuggled_after_a_semicolon_is_refused() -> None:
    """The classic. One question means one statement."""
    with pytest.raises(GuardrailViolation):
        guard("SELECT 1 FROM student_360; DROP TABLE users", _open_scope())


def test_reading_any_other_table_is_refused() -> None:
    """student_360 is the only thing on offer; users holds password hashes."""
    with pytest.raises(GuardrailViolation) as exc:
        guard("SELECT email FROM users", _open_scope())
    assert "student_360" in exc.value.reason


def test_schema_qualifying_the_view_is_refused() -> None:
    """The one escape that would work if it were allowed.

    The boundary is a CTE bound to the bare name `student_360`. `public.student_360`
    resolves past the CTE to the unscoped view, so the qualified form cannot be permitted.
    """
    with pytest.raises(GuardrailViolation) as exc:
        guard("SELECT full_name FROM public.student_360", _open_scope())
    assert "qualified" in exc.value.reason.lower()


def test_filesystem_and_sleep_functions_are_refused() -> None:
    with pytest.raises(GuardrailViolation):
        guard("SELECT pg_sleep(30) FROM student_360", _open_scope())


def test_a_markdown_fence_is_stripped_rather_than_rejected() -> None:
    """Models fence their SQL whatever the instructions say. Not worth failing over."""
    guarded = guard("```sql\nSELECT full_name FROM student_360\n```", _open_scope())
    assert "student_360" in guarded.executed_sql


def test_the_row_cap_is_applied_even_when_the_model_asks_for_more() -> None:
    guarded = guard("SELECT full_name FROM student_360 LIMIT 100000", _open_scope(), row_limit=25)
    assert guarded.row_limit == 25
    assert "25" in guarded.executed_sql


def test_the_scope_cte_is_prepended_before_a_model_written_cte() -> None:
    """Order is the whole trick.

    PostgreSQL resolves a CTE against those declared before it. If ours were appended, a
    model-defined CTE reading student_360 would reach the unscoped view.
    """
    guarded = guard(
        "WITH low AS (SELECT * FROM student_360 WHERE mastery_percent < 50) "
        "SELECT full_name FROM low",
        _open_scope(),
    )
    executed = guarded.executed_sql.lower()
    assert executed.index("student_360 as") < executed.index("low as")


# ------------------------------------------------------------------- endpoint


@pytest.fixture()
def api(client: TestClient, clean_db: str) -> Iterator[TestClient]:
    engine = create_engine(to_sync_url(clean_db), pool_pre_ping=True)
    with Session(engine) as session:
        generate_school(session, TEST_SPEC)
        session.commit()
    engine.dispose()
    yield client


@pytest.fixture()
def model_writes(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Pin what the 'model' returns, so the platform's behaviour is what is measured."""

    def _install(sql: str | None = None, declined: str | None = None) -> None:
        async def _fake(_question: str) -> service.ModelReply:
            return service.ModelReply(sql=sql, declined=declined)

        monkeypatch.setattr(service, "_openrouter_writer", _fake)

    return _install


def _headers(api: TestClient, email: str) -> dict[str, str]:
    response = api.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD, "institution_name": SCHOOL},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _ask(api: TestClient, email: str, question: str, limit: int = 500) -> dict:
    response = api.post(
        "/api/v1/ask/students",
        json={"question": question, "limit": limit},
        headers=_headers(api, email),
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_one_question_one_query_three_different_answers(api: TestClient, model_writes) -> None:  # type: ignore[no-untyped-def]
    """The point of the whole exercise, in one assertion.

    Identical question, identical generated SQL, three callers. Nothing about who is asking
    reaches the model — the difference comes entirely from the boundary applied afterwards.
    """
    model_writes(sql=LIST_EVERYTHING)

    admin = _ask(api, ADMIN, "list every student and their mastery")
    teacher = _ask(api, TEACHER, "list every student and their mastery")
    student = _ask(api, STUDENT, "list every student and their mastery")

    assert admin["row_count"] == 150, "5 grades x 2 sections x 3 students x 5 subjects"
    assert teacher["row_count"] == 9, "Grade 8 Maths (6) + Grade 9 Science section A (3)"
    assert student["row_count"] == 5, "her own five subjects"

    assert admin["model_sql"] == teacher["model_sql"] == student["model_sql"]


def test_teacher_asking_about_a_grade_she_does_not_teach_gets_zero_rows(
    api: TestClient, model_writes
) -> None:  # type: ignore[no-untyped-def]
    """Zero rows and no error. An error would confirm Grade 10 exists."""
    model_writes(sql=f"{LIST_EVERYTHING} WHERE grade = 'Grade 10'")
    body = _ask(api, TEACHER, "how is Grade 10 doing")
    assert body["answered"] is True
    assert body["row_count"] == 0


def test_a_teacher_cannot_reach_another_subject_through_a_question(
    api: TestClient, model_writes
) -> None:  # type: ignore[no-untyped-def]
    """The Stage 1 leak, retested through the question path."""
    model_writes(sql=f"{LIST_EVERYTHING} WHERE subject = 'English'")
    body = _ask(api, TEACHER, "show me English marks")
    assert body["row_count"] == 0


def test_the_query_that_ran_is_returned_with_the_answer(api: TestClient, model_writes) -> None:  # type: ignore[no-untyped-def]
    """A number a teacher cannot check is a number a teacher should not trust."""
    model_writes(sql=LIST_EVERYTHING)
    body = _ask(api, ADMIN, "list every student")
    assert body["model_sql"] == LIST_EVERYTHING
    assert "WITH" in body["executed_sql"].upper(), "the boundary must be visible, not implied"
    assert "institution_id" in body["executed_sql"]


def test_an_unanswerable_question_says_so_instead_of_inventing(
    api: TestClient, model_writes
) -> None:  # type: ignore[no-untyped-def]
    model_writes(declined="This data holds no fee information.")
    body = _ask(api, ADMIN, "which students have unpaid fees")
    assert body["answered"] is False
    assert "fee" in body["reason"].lower()
    assert body["executed_sql"] is None
    assert body["rows"] == []


def test_a_write_attempt_is_refused_and_explained(api: TestClient, model_writes) -> None:  # type: ignore[no-untyped-def]
    model_writes(sql="DELETE FROM student_360")
    body = _ask(api, ADMIN, "delete everything")
    assert body["answered"] is False
    assert body["rows"] == []


def test_every_question_is_audited_including_the_refused_ones(
    api: TestClient, model_writes
) -> None:  # type: ignore[no-untyped-def]
    """The refused attempts are the entries worth having."""
    model_writes(sql="SELECT email FROM users")
    _ask(api, TEACHER, "show me everyone's email address")

    events = api.get(
        "/api/v1/admin/audit-events?event_type=data.scoped_read",
        headers=_headers(api, ADMIN),
    ).json()
    asks = [e for e in events if e["entity_type"] == "nl_query.students"]
    assert asks, "the attempt must be recorded"
    assert asks[0]["payload"]["rows_returned"] == 0
    assert "email address" in asks[0]["payload"]["detail"]

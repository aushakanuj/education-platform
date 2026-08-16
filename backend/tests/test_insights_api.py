"""End-to-end tests through the HTTP layer.

The scope tests call `query_student_360` directly, which left the router itself untested --
and a real bug hid there: the handler used `row.__dict__` on a slots dataclass, which has
none, so every request 500'd while every unit test passed. These tests exercise the actual
endpoints so that gap cannot reopen.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from education_platform.db.url import to_sync_url
from education_platform.modules.synthetic.generator import SchoolSpec, generate_school

TEST_SPEC = SchoolSpec(sections_per_grade=2, students_per_section=3, term_weeks=2)
SCHOOL = TEST_SPEC.institution_name
PASSWORD = "demo1234"

ADMIN = "fatima.almansouri@alnoor.school"
TEACHER = "meera.krishnan@alnoor.school"


@pytest.fixture()
def api(client: TestClient, clean_db: str) -> Iterator[TestClient]:
    """The app, backed by a generated school."""
    engine = create_engine(to_sync_url(clean_db), pool_pre_ping=True)
    with Session(engine) as session:
        generate_school(session, TEST_SPEC)
        session.commit()
    engine.dispose()
    yield client


def _headers(api: TestClient, email: str) -> dict[str, str]:
    response = api.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD, "institution_name": SCHOOL},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _student_email(api: TestClient) -> str:
    """Any student in the generated school -- the rule under test holds for all of them."""
    return "student25@alnoor.school"


def test_same_endpoint_returns_different_answers_per_role(api: TestClient) -> None:
    """The whole security model, visible in one assertion."""
    admin = api.get("/api/v1/insights/students?limit=500", headers=_headers(api, ADMIN)).json()
    teacher = api.get("/api/v1/insights/students?limit=500", headers=_headers(api, TEACHER)).json()

    assert admin["rows_returned"] > teacher["rows_returned"] > 0
    assert admin["scope_description"] == "Whole institution"
    assert "assignment" in teacher["scope_description"]


def test_endpoint_returns_real_rows_not_a_server_error(api: TestClient) -> None:
    """Guards the bug this file exists for: the handler must serialise its rows."""
    response = api.get("/api/v1/insights/students?limit=5", headers=_headers(api, ADMIN))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["items"], "the endpoint must return rows, not just a count"
    first = body["items"][0]
    for field in ("student_id", "full_name", "grade", "subject", "mastery_percent"):
        assert field in first


def test_teacher_asking_about_another_grade_gets_empty_not_forbidden(
    api: TestClient,
) -> None:
    """200 with zero rows. A 403 would confirm the grade exists."""
    response = api.get("/api/v1/insights/students?grade=Grade%2010", headers=_headers(api, TEACHER))
    assert response.status_code == 200
    assert response.json()["rows_returned"] == 0


def test_teacher_asking_about_a_subject_they_do_not_teach_gets_empty(api: TestClient) -> None:
    """Her Grade 8 pupils all take English; she teaches them Mathematics, so: nothing."""
    headers = _headers(api, TEACHER)
    english = api.get("/api/v1/insights/students?subject=English", headers=headers).json()
    maths = api.get("/api/v1/insights/students?subject=Mathematics", headers=headers).json()

    assert english["rows_returned"] == 0
    assert maths["rows_returned"] > 0


def test_teacher_cannot_open_the_admin_audit_screen(api: TestClient) -> None:
    """Capability is refused even though content is empty. Different failures."""
    response = api.get("/api/v1/admin/audit-events", headers=_headers(api, TEACHER))
    assert response.status_code == 403


def test_each_read_writes_exactly_one_audit_entry_with_its_row_count(
    api: TestClient,
) -> None:
    """One read, one audit row -- and the row count must be on it."""
    admin_headers = _headers(api, ADMIN)
    api.get("/api/v1/insights/students?limit=5", headers=admin_headers)

    events = api.get(
        "/api/v1/admin/audit-events?event_type=data.scoped_read", headers=admin_headers
    ).json()
    reads = [e for e in events if e["entity_type"] == "insights.students"]
    assert len(reads) == 1, "a single request must not produce two audit entries"
    assert reads[0]["payload"]["rows_returned"] == 5


def test_a_refused_read_is_still_recorded(api: TestClient) -> None:
    """The zero-row entry is the evidence the boundary held, so it must be kept."""
    api.get("/api/v1/insights/students?grade=Grade%2010", headers=_headers(api, TEACHER))

    events = api.get(
        "/api/v1/admin/audit-events?event_type=data.scoped_read",
        headers=_headers(api, ADMIN),
    ).json()
    zero_row_reads = [e for e in events if e["payload"].get("rows_returned") == 0]
    assert zero_row_reads, "an out-of-scope read must appear in the audit trail"
    assert "Grade 10" in zero_row_reads[0]["payload"].get("detail", "")


def test_student_sees_only_their_own_record(api: TestClient) -> None:
    headers = _headers(api, _student_email(api))
    body = api.get("/api/v1/insights/students", headers=headers).json()
    assert body["scope_description"] == "Your own record only"
    assert {item["full_name"] for item in body["items"]} == {body["items"][0]["full_name"]}

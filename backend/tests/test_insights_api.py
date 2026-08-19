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


# ------------------------------------------------------- one student's detail page


def _some_student_of(api: TestClient, email: str) -> str:
    rows = api.get("/api/v1/insights/students?limit=500", headers=_headers(api, email)).json()
    assert rows["items"], f"{email} should be able to see somebody"
    return str(rows["items"][0]["student_id"])


def test_a_teacher_opening_a_pupil_sees_only_the_subjects_she_teaches(api: TestClient) -> None:
    """The same rule as the list, on a single record: her pupils, her subjects.

    Their English marks exist and belong to the same child. They are not hers to open.
    """
    headers = _headers(api, TEACHER)
    student_id = _some_student_of(api, TEACHER)

    body = api.get(f"/api/v1/insights/students/{student_id}", headers=headers).json()

    assert {s["subject"] for s in body["subjects"]} <= {"Mathematics", "Science"}
    assert "English" not in {s["subject"] for s in body["subjects"]}


def test_an_administrator_opening_the_same_pupil_sees_every_subject(api: TestClient) -> None:
    """Proves the narrowing above is the boundary and not simply missing data."""
    student_id = _some_student_of(api, TEACHER)

    teacher = api.get(
        f"/api/v1/insights/students/{student_id}", headers=_headers(api, TEACHER)
    ).json()
    admin = api.get(f"/api/v1/insights/students/{student_id}", headers=_headers(api, ADMIN)).json()

    assert len(admin["subjects"]) > len(teacher["subjects"])
    assert "English" in {s["subject"] for s in admin["subjects"]}


def test_the_attempt_history_is_narrowed_to_the_same_subjects(api: TestClient) -> None:
    """The history is the part most likely to leak: it is a different table entirely."""
    student_id = _some_student_of(api, TEACHER)
    body = api.get(f"/api/v1/insights/students/{student_id}", headers=_headers(api, TEACHER)).json()

    permitted = {s["subject"] for s in body["subjects"]}
    assert {a["subject"] for a in body["attempts"]} <= permitted


def test_a_teacher_opening_a_pupil_who_is_not_hers_gets_404_not_403(api: TestClient) -> None:
    """404, the same answer as a student who does not exist.

    A 403 would say "this child exists, but not for you" -- which is itself the disclosure.
    """
    mine = {
        item["student_id"]
        for item in api.get(
            "/api/v1/insights/students?limit=500", headers=_headers(api, TEACHER)
        ).json()["items"]
    }
    everyone = {
        item["student_id"]
        for item in api.get(
            "/api/v1/insights/students?limit=500", headers=_headers(api, ADMIN)
        ).json()["items"]
    }
    outsider = next(iter(everyone - mine))

    response = api.get(f"/api/v1/insights/students/{outsider}", headers=_headers(api, TEACHER))
    assert response.status_code == 404


def test_an_invented_student_id_gives_the_same_404(api: TestClient) -> None:
    """The two failures must be indistinguishable, or the difference is the leak."""
    response = api.get(
        "/api/v1/insights/students/00000000-0000-0000-0000-000000000001",
        headers=_headers(api, TEACHER),
    )
    assert response.status_code == 404


def test_a_student_can_open_their_own_record_but_not_a_classmate(api: TestClient) -> None:
    headers = _headers(api, _student_email(api))
    me = api.get("/api/v1/insights/students", headers=headers).json()["items"][0]["student_id"]

    assert api.get(f"/api/v1/insights/students/{me}", headers=headers).status_code == 200

    classmate = next(
        item["student_id"]
        for item in api.get(
            "/api/v1/insights/students?limit=500", headers=_headers(api, ADMIN)
        ).json()["items"]
        if item["student_id"] != me
    )
    assert api.get(f"/api/v1/insights/students/{classmate}", headers=headers).status_code == 404


def test_the_detail_page_carries_attendance_and_a_reason_to_worry(api: TestClient) -> None:
    """Whole-day attendance is not a subject's to divide, so it is reported once."""
    student_id = _some_student_of(api, ADMIN)
    body = api.get(f"/api/v1/insights/students/{student_id}", headers=_headers(api, ADMIN)).json()

    assert body["days_counted"] > 0
    assert 0 <= body["attendance_percent"] <= 100
    assert all(row["status"] != "present" for row in body["absences"])


def test_a_refused_detail_read_is_still_audited(api: TestClient) -> None:
    """Opening a child who is not yours is exactly the access worth having a record of."""
    api.get(
        "/api/v1/insights/students/00000000-0000-0000-0000-000000000001",
        headers=_headers(api, TEACHER),
    )

    events = api.get(
        "/api/v1/admin/audit-events?event_type=data.scoped_read", headers=_headers(api, ADMIN)
    ).json()
    refused = [e for e in events if e["entity_type"] == "insights.student_detail"]
    assert refused, "a refused detail read must appear in the audit trail"
    assert refused[0]["payload"]["rows_returned"] == 0
    assert "not in scope" in refused[0]["payload"]["detail"]

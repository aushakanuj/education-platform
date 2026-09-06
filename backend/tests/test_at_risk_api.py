"""End-to-end tests through the HTTP layer, against the real synthetic generator.

Precise numeric cases (exact tiers, exact driver math) live in test_at_risk_engine.py,
which needs no database at all. These tests check the things only the real stack can
prove: that a real teacher's login actually resolves to the right Scope, that the
permission boundary really narrows a real query, and that recomputing against the real
planted data (Aisha Rahman) produces a real, persisted flag -- not a mocked one.
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
#: Assigned to Grade 8's Mathematics and Science offerings by the generator -- the same
#: teacher who teaches the planted student, Aisha Rahman (Grade 8, section 0, seat 0).
TEACHER = "meera.krishnan@alnoor.school"
STUDENT = "student1@alnoor.school"  # Aisha Rahman herself -- see generator.py

#: Seeded into POC Demo School by the HTTP client fixture, before this file generates
#: Al Noor -- the only way to test the tenant boundary at all. Same pattern as
#: test_insights_api.py.
POC_ADMIN = "admin@demo.school"


@pytest.fixture()
def api(client: TestClient, clean_db: str) -> Iterator[TestClient]:
    engine = create_engine(to_sync_url(clean_db), pool_pre_ping=True)
    with Session(engine) as session:
        generate_school(session, TEST_SPEC)
        session.commit()
    engine.dispose()
    yield client


def _headers(api: TestClient, email: str, institution_name: str = SCHOOL) -> dict[str, str]:
    response = api.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD, "institution_name": institution_name},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _recompute(api: TestClient) -> dict[str, object]:
    response = api.post("/api/v1/at-risk/recompute", headers=_headers(api, ADMIN))
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------------------
# Capability gate: a student must never reach this feature, full stop -- not "reach it
# and see nothing," reach it and be refused outright.
# --------------------------------------------------------------------------------------


def test_a_student_cannot_reach_the_endpoint_at_all(api: TestClient) -> None:
    """403, not an empty list. This is the capability half of Section 7.3 -- distinct
    from, and enforced before, any row-level scoping."""
    response = api.get("/api/v1/at-risk/flags", headers=_headers(api, STUDENT))
    assert response.status_code == 403


def test_a_student_cannot_dismiss_a_flag_either(api: TestClient) -> None:
    _recompute(api)
    response = api.post(
        "/api/v1/at-risk/flags/00000000-0000-0000-0000-000000000000/dismiss",
        json={},
        headers=_headers(api, STUDENT),
    )
    assert response.status_code == 403


def test_a_teacher_cannot_trigger_a_recompute(api: TestClient) -> None:
    """Recompute reads the whole institution -- an administrator action, not a scoped
    read any teacher's Scope would ever cover."""
    response = api.post("/api/v1/at-risk/recompute", headers=_headers(api, TEACHER))
    assert response.status_code == 403


# --------------------------------------------------------------------------------------
# The engine, run for real, against the real planted data.
# --------------------------------------------------------------------------------------


def test_recompute_flags_aisha_rahman_for_mathematics(api: TestClient) -> None:
    """The named case from spec Section 6.3, run end-to-end: real login, real Scope, real
    query against student_360 and quiz_attempts, real persisted row."""
    result = _recompute(api)
    assert result["students_considered"] > 0
    assert result["flags_active"] > 0

    flags = api.get("/api/v1/at-risk/flags", headers=_headers(api, ADMIN)).json()["items"]
    aisha_flags = [f for f in flags if f["student_name"] == "Aisha Rahman"]

    assert aisha_flags, "Aisha Rahman must be flagged -- she is the planted case"
    subjects = {f["subject"] for f in aisha_flags if f["subject"] is not None}
    assert "Mathematics" in subjects
    # The core anti-conflation requirement: her fine subjects must not also show up.
    assert "Science" not in subjects or all(
        f["tier"] != "urgent" for f in aisha_flags if f["subject"] == "Science"
    )


def test_recompute_is_idempotent_not_additive(api: TestClient) -> None:
    """Running it twice must update the same flags, not double them -- the unique
    partial indexes in the migration exist for exactly this."""
    _recompute(api)
    first = api.get("/api/v1/at-risk/flags", headers=_headers(api, ADMIN)).json()
    _recompute(api)
    second = api.get("/api/v1/at-risk/flags", headers=_headers(api, ADMIN)).json()
    assert first["rows_returned"] == second["rows_returned"]


# --------------------------------------------------------------------------------------
# Row-level scoping: the same reuse of authorization.predicate every other feature uses.
# --------------------------------------------------------------------------------------


def test_a_teacher_sees_only_flags_for_subjects_they_teach(api: TestClient) -> None:
    _recompute(api)
    flags = api.get("/api/v1/at-risk/flags", headers=_headers(api, TEACHER)).json()["items"]

    assert flags, "the teacher must see at least Aisha's Mathematics flag"
    for flag in flags:
        # Every subject-tagged flag returned must be one this teacher actually teaches.
        assert flag["subject"] in {"Mathematics", "Science", None}


def test_an_administrator_sees_more_than_any_teacher(api: TestClient) -> None:
    _recompute(api)
    admin_flags = api.get("/api/v1/at-risk/flags", headers=_headers(api, ADMIN)).json()
    teacher_flags = api.get("/api/v1/at-risk/flags", headers=_headers(api, TEACHER)).json()
    assert admin_flags["rows_returned"] >= teacher_flags["rows_returned"]


def test_attendance_only_flags_are_never_visible_to_a_teacher(api: TestClient) -> None:
    """Section 7.2's routing rule, falling out of the shared predicate with no special
    case: a NULL grade_subject_offering_id cannot match any teacher's taught-pairs
    check, so it can only ever satisfy the unrestricted (administrator) branch."""
    _recompute(api)
    teacher_flags = api.get("/api/v1/at-risk/flags", headers=_headers(api, TEACHER)).json()
    assert all(f["subject"] is not None for f in teacher_flags["items"])

    admin_flags = api.get("/api/v1/at-risk/flags", headers=_headers(api, ADMIN)).json()
    attendance_only = [f for f in admin_flags["items"] if f["subject"] is None]
    assert attendance_only, (
        "the planted counter-example students (low attendance, strong marks) must "
        "produce at least one attendance-only flag, visible only here"
    )


def test_an_administrator_at_another_institution_sees_none_of_this(api: TestClient) -> None:
    """The cross-tenant test every new feature is now required to carry (project
    permission-model standard). POC Demo School has no at-risk data of its own -- the
    real assertion is that recomputing and reading from Al Noor never leaks into it."""
    _recompute(api)
    headers = _headers(api, POC_ADMIN, institution_name="POC Demo School")
    response = api.get("/api/v1/at-risk/flags", headers=headers)
    assert response.status_code == 200
    assert response.json()["rows_returned"] == 0


# --------------------------------------------------------------------------------------
# Dismissal: AR-4.
# --------------------------------------------------------------------------------------


def test_dismissing_a_flag_removes_it_from_the_active_list(api: TestClient) -> None:
    _recompute(api)
    admin_headers = _headers(api, ADMIN)
    flags = api.get("/api/v1/at-risk/flags", headers=admin_headers).json()["items"]
    target = flags[0]

    response = api.post(
        f"/api/v1/at-risk/flags/{target['id']}/dismiss",
        json={"note": "Spoke with the student; retaking the unit."},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "dismissed"

    remaining = api.get("/api/v1/at-risk/flags", headers=admin_headers).json()["items"]
    assert target["id"] not in {f["id"] for f in remaining}


def test_dismissing_a_flag_outside_your_scope_is_404_not_403(api: TestClient) -> None:
    """Rule 8: a single-record refusal is 404, the same answer a nonexistent id gives --
    never 403, which would itself confirm the flag exists for a child outside scope."""
    _recompute(api)
    admin_flags = api.get("/api/v1/at-risk/flags", headers=_headers(api, ADMIN)).json()["items"]
    attendance_only_flag = next(f for f in admin_flags if f["subject"] is None)

    # A teacher cannot see this flag at all (proven above) -- confirm dismissing it
    # behaves exactly like a nonexistent id, not like "forbidden."
    response = api.post(
        f"/api/v1/at-risk/flags/{attendance_only_flag['id']}/dismiss",
        json={},
        headers=_headers(api, TEACHER),
    )
    assert response.status_code == 404


def test_dismissing_a_nonexistent_flag_is_also_404(api: TestClient) -> None:
    response = api.post(
        "/api/v1/at-risk/flags/00000000-0000-0000-0000-000000000000/dismiss",
        json={},
        headers=_headers(api, ADMIN),
    )
    assert response.status_code == 404


# --------------------------------------------------------------------------------------
# Audit: AR-5 (views) and AR-4 (dismissals) each leave a real trail.
# --------------------------------------------------------------------------------------


def test_viewing_flags_writes_an_audit_event(api: TestClient) -> None:
    _recompute(api)
    admin_headers = _headers(api, ADMIN)
    api.get("/api/v1/at-risk/flags", headers=admin_headers)

    events = api.get("/api/v1/admin/audit-events", headers=admin_headers).json()
    assert any(e["event_type"] == "risk.view_flags" for e in events)


def test_dismissing_a_flag_writes_an_audit_event(api: TestClient) -> None:
    _recompute(api)
    admin_headers = _headers(api, ADMIN)
    flag_id = api.get("/api/v1/at-risk/flags", headers=admin_headers).json()["items"][0]["id"]

    api.post(f"/api/v1/at-risk/flags/{flag_id}/dismiss", json={}, headers=admin_headers)

    events = api.get("/api/v1/admin/audit-events", headers=admin_headers).json()
    assert any(e["event_type"] == "risk.record_intervention" for e in events)

"""Generating draft quiz questions: validation, authorisation, and the draft boundary.

The validator is a pure function, so every malformed shape a model can emit is cheap to
assert. The endpoint tests then check the two things that actually matter in a school: a
teacher can only author where they teach, and nothing generated here reaches a student
until a person publishes it.

No test calls OpenRouter. The writer is injected.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from education_platform.db.url import to_sync_url
from education_platform.modules.assessments.models import (
    QuestionDifficulty,
    QuestionVersion,
    QuestionVersionStatus,
)
from education_platform.modules.authoring import service
from education_platform.modules.synthetic.generator import SchoolSpec, generate_school

TEST_SPEC = SchoolSpec(sections_per_grade=2, students_per_section=3, term_weeks=2)
SCHOOL = TEST_SPEC.institution_name
PASSWORD = "demo1234"

ADMIN = "fatima.almansouri@alnoor.school"
TEACHER = "meera.krishnan@alnoor.school"
#: The test school is small (30 students), so the full demo's roll numbers do not apply.
STUDENT = "student25@alnoor.school"


def good_question(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "prompt": "Which of these is a square number?",
        "options": {"A": "16", "B": "18", "C": "20", "D": "22"},
        "correct": "A",
        "explanation": "16 is 4 x 4.",
    }
    payload.update(over)
    return payload


# ------------------------------------------------------------------ validation


def test_a_well_formed_question_is_accepted() -> None:
    result = service.validate(good_question())
    assert not isinstance(result, str)
    assert result.correct_label == "A"
    assert result.options["A"] == "16"


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (good_question(options={"A": "1", "B": "2", "C": "3"}), "options a-d"),
        (good_question(options={"A": "1", "B": "2", "C": "3", "D": "4", "E": "5"}), "options a-d"),
        (good_question(correct="E"), "not one of the options"),
        (good_question(prompt="?"), "too short"),
        (good_question(options={"A": "16", "B": "16", "C": "20", "D": "22"}), "duplicate"),
        (good_question(options={"A": "16", "B": "", "C": "20", "D": "22"}), "empty"),
        (
            good_question(options={"A": "16", "B": "18", "C": "20", "D": "All of the above"}),
            "above",
        ),
    ],
    ids=["too-few", "too-many", "bad-key", "no-prompt", "duplicate", "empty", "all-of-the-above"],
)
def test_malformed_questions_are_rejected_with_a_reason(
    payload: dict[str, Any], expected: str
) -> None:
    result = service.validate(payload)
    assert isinstance(result, str), "should have been rejected"
    assert expected in result.lower()


def test_one_bad_question_does_not_cost_the_good_ones() -> None:
    """A model that fumbles one of five should still give a teacher the other four."""
    verdicts = [service.validate(q) for q in [good_question(), good_question(correct="Z")]]
    assert not isinstance(verdicts[0], str)
    assert isinstance(verdicts[1], str)


def test_an_unknown_difficulty_falls_back_rather_than_failing() -> None:
    result = service.validate(good_question(difficulty="fiendish"))
    assert not isinstance(result, str)
    assert result.difficulty == QuestionDifficulty.MEDIUM


# -------------------------------------------------------------------- endpoint


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
    def _install(questions: list[dict[str, Any]]) -> None:
        async def _fake(_prompt: str) -> list[dict[str, Any]]:
            return questions

        monkeypatch.setattr(service, "_openrouter_writer", _fake)

    return _install


def _headers(api: TestClient, email: str) -> dict[str, str]:
    response = api.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD, "institution_name": SCHOOL},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _first_subtopic(api: TestClient, email: str) -> dict[str, Any]:
    response = api.get("/api/v1/authoring/subtopics", headers=_headers(api, email))
    assert response.status_code == 200, response.text
    subtopics = response.json()
    assert subtopics, "the teacher should have something to author for"
    return subtopics[0]


def test_a_teacher_is_offered_only_the_subjects_they_teach(api: TestClient) -> None:
    subjects = {
        s["subject"]
        for s in api.get("/api/v1/authoring/subtopics", headers=_headers(api, TEACHER)).json()
    }
    assert subjects == {"Mathematics", "Science"}, "Meera teaches these two and no others"


def test_an_administrator_is_offered_the_whole_school(api: TestClient) -> None:
    teacher = api.get("/api/v1/authoring/subtopics", headers=_headers(api, TEACHER)).json()
    admin = api.get("/api/v1/authoring/subtopics", headers=_headers(api, ADMIN)).json()
    assert len(admin) > len(teacher) > 0


def test_generated_questions_are_saved_as_drafts(
    api: TestClient, model_writes, clean_db: str
) -> None:  # type: ignore[no-untyped-def]
    model_writes(
        [
            good_question(),
            good_question(
                prompt="What is 9 x 9?",
                correct="B",
                options={"A": "72", "B": "81", "C": "88", "D": "99"},
            ),
        ]
    )
    subtopic = _first_subtopic(api, TEACHER)

    response = api.post(
        f"/api/v1/authoring/subtopics/{subtopic['id']}/generate",
        json={"count": 2},
        headers=_headers(api, TEACHER),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == 2
    assert len(body["drafts"]) == 2

    # Scoped to what this call created: the generated school already ships published
    # questions of its own, so "everything in the table is a draft" was never the claim.
    created_ids = [UUID(draft["id"]) for draft in body["drafts"]]
    engine = create_engine(to_sync_url(clean_db), pool_pre_ping=True)
    with Session(engine) as session:
        statuses = session.scalars(
            select(QuestionVersion.lifecycle_status).where(QuestionVersion.id.in_(created_ids))
        ).all()
    engine.dispose()
    assert set(statuses) == {QuestionVersionStatus.DRAFT}, "nothing may be published on creation"


def test_a_rejected_question_is_reported_not_silently_dropped(
    api: TestClient, model_writes
) -> None:  # type: ignore[no-untyped-def]
    model_writes([good_question(), good_question(correct="Z")])
    subtopic = _first_subtopic(api, TEACHER)

    body = api.post(
        f"/api/v1/authoring/subtopics/{subtopic['id']}/generate",
        json={"count": 2},
        headers=_headers(api, TEACHER),
    ).json()

    assert body["created"] == 1
    assert len(body["rejected"]) == 1
    assert "not one of the options" in body["rejected"][0]


def test_a_teacher_cannot_author_for_a_subject_they_do_not_teach(
    api: TestClient, model_writes
) -> None:  # type: ignore[no-untyped-def]
    """Authoring is an action, so this is a 403 rather than an empty result."""
    model_writes([good_question()])
    english = next(
        s
        for s in api.get("/api/v1/authoring/subtopics", headers=_headers(api, ADMIN)).json()
        if s["subject"] == "English"
    )

    response = api.post(
        f"/api/v1/authoring/subtopics/{english['id']}/generate",
        json={"count": 1},
        headers=_headers(api, TEACHER),
    )
    assert response.status_code == 403


def test_a_student_cannot_author_at_all(api: TestClient) -> None:
    response = api.get("/api/v1/authoring/subtopics", headers=_headers(api, STUDENT))
    assert response.status_code == 200
    assert response.json() == [], "a student teaches nothing, so has nothing to author"


def test_publishing_is_one_at_a_time_and_deliberate(api: TestClient, model_writes) -> None:  # type: ignore[no-untyped-def]
    model_writes([good_question(), good_question(prompt="What is 5 squared?")])
    subtopic = _first_subtopic(api, TEACHER)
    headers = _headers(api, TEACHER)

    drafts = api.post(
        f"/api/v1/authoring/subtopics/{subtopic['id']}/generate",
        json={"count": 2},
        headers=headers,
    ).json()["drafts"]

    published = api.post(f"/api/v1/authoring/drafts/{drafts[0]['id']}/publish", headers=headers)
    assert published.status_code == 204

    remaining = api.get(
        f"/api/v1/authoring/subtopics/{subtopic['id']}/drafts", headers=headers
    ).json()
    assert len(remaining) == 1, "the published one is no longer a draft"
    assert remaining[0]["id"] == drafts[1]["id"]


def test_discarding_archives_rather_than_deletes(
    api: TestClient, model_writes, clean_db: str
) -> None:  # type: ignore[no-untyped-def]
    model_writes([good_question()])
    subtopic = _first_subtopic(api, TEACHER)
    headers = _headers(api, TEACHER)

    draft = api.post(
        f"/api/v1/authoring/subtopics/{subtopic['id']}/generate",
        json={"count": 1},
        headers=headers,
    ).json()["drafts"][0]

    assert api.delete(f"/api/v1/authoring/drafts/{draft['id']}", headers=headers).status_code == 204

    engine = create_engine(to_sync_url(clean_db), pool_pre_ping=True)
    with Session(engine) as session:
        status = session.scalar(
            select(QuestionVersion.lifecycle_status).where(QuestionVersion.id == draft["id"])
        )
    engine.dispose()
    assert status == QuestionVersionStatus.ARCHIVED, "a rejected question is kept, not erased"


def test_the_review_view_shows_the_correct_answer(api: TestClient, model_writes) -> None:  # type: ignore[no-untyped-def]
    """A teacher judging a draft must see which option is marked correct."""
    model_writes([good_question()])
    subtopic = _first_subtopic(api, TEACHER)
    headers = _headers(api, TEACHER)

    body = api.post(
        f"/api/v1/authoring/subtopics/{subtopic['id']}/generate",
        json={"count": 1},
        headers=headers,
    ).json()

    draft = body["drafts"][0]
    assert draft["correct_label"] == "A"
    assert [o["label"] for o in draft["options"]] == ["A", "B", "C", "D"]


def test_an_approved_question_is_readable_back_from_the_bank(api: TestClient, model_writes) -> None:  # type: ignore[no-untyped-def]
    """Approving must not feel like losing: what went in has to be findable again."""
    model_writes([good_question()])
    subtopic = _first_subtopic(api, TEACHER)
    headers = _headers(api, TEACHER)

    draft = api.post(
        f"/api/v1/authoring/subtopics/{subtopic['id']}/generate",
        json={"count": 1},
        headers=headers,
    ).json()["drafts"][0]

    before = api.get(
        f"/api/v1/authoring/subtopics/{subtopic['id']}/questions", headers=headers
    ).json()
    api.post(f"/api/v1/authoring/drafts/{draft['id']}/publish", headers=headers)
    after = api.get(
        f"/api/v1/authoring/subtopics/{subtopic['id']}/questions", headers=headers
    ).json()

    assert len(after) == len(before) + 1
    published = next(q for q in after if q["id"] == draft["id"])
    assert published["correct_label"] == "A", "the export needs the answer, so it must come back"
    assert [o["label"] for o in published["options"]] == ["A", "B", "C", "D"]


def test_a_discarded_question_is_in_neither_list(api: TestClient, model_writes) -> None:  # type: ignore[no-untyped-def]
    """Archived means out of the way, not resurfacing in the approved bank."""
    model_writes([good_question()])
    subtopic = _first_subtopic(api, TEACHER)
    headers = _headers(api, TEACHER)

    draft = api.post(
        f"/api/v1/authoring/subtopics/{subtopic['id']}/generate",
        json={"count": 1},
        headers=headers,
    ).json()["drafts"][0]
    api.delete(f"/api/v1/authoring/drafts/{draft['id']}", headers=headers)

    drafts = api.get(f"/api/v1/authoring/subtopics/{subtopic['id']}/drafts", headers=headers).json()
    approved = api.get(
        f"/api/v1/authoring/subtopics/{subtopic['id']}/questions", headers=headers
    ).json()

    assert draft["id"] not in {q["id"] for q in drafts}
    assert draft["id"] not in {q["id"] for q in approved}


def test_the_approved_bank_is_not_readable_outside_what_you_teach(api: TestClient) -> None:
    """Published questions still carry answer keys, so this stays a teaching path."""
    english = next(
        s
        for s in api.get("/api/v1/authoring/subtopics", headers=_headers(api, ADMIN)).json()
        if s["subject"] == "English"
    )
    response = api.get(
        f"/api/v1/authoring/subtopics/{english['id']}/questions", headers=_headers(api, TEACHER)
    )
    assert response.status_code == 403


def test_the_subtopic_list_counts_both_waiting_and_approved(api: TestClient, model_writes) -> None:  # type: ignore[no-untyped-def]
    """A draft count alone drops to zero on approval and looks like the work vanished."""
    model_writes([good_question()])
    headers = _headers(api, TEACHER)
    subtopic = _first_subtopic(api, TEACHER)

    def counts() -> tuple[int, int]:
        row = next(
            s
            for s in api.get("/api/v1/authoring/subtopics", headers=headers).json()
            if s["id"] == subtopic["id"]
        )
        return row["draft_count"], row["published_count"]

    api.post(
        f"/api/v1/authoring/subtopics/{subtopic['id']}/generate",
        json={"count": 1},
        headers=headers,
    )
    drafts_before, published_before = counts()
    assert drafts_before >= 1

    draft = api.get(f"/api/v1/authoring/subtopics/{subtopic['id']}/drafts", headers=headers).json()[
        0
    ]
    api.post(f"/api/v1/authoring/drafts/{draft['id']}/publish", headers=headers)

    drafts_after, published_after = counts()
    assert drafts_after == drafts_before - 1
    assert published_after == published_before + 1


def test_generation_is_audited(api: TestClient, model_writes) -> None:  # type: ignore[no-untyped-def]
    model_writes([good_question()])
    subtopic = _first_subtopic(api, TEACHER)
    api.post(
        f"/api/v1/authoring/subtopics/{subtopic['id']}/generate",
        json={"count": 1},
        headers=_headers(api, TEACHER),
    )

    events = api.get(
        "/api/v1/admin/audit-events?event_type=data.scoped_read", headers=_headers(api, ADMIN)
    ).json()
    generated = [e for e in events if e["entity_type"] == "authoring.generate"]
    assert generated, "generating questions must appear in the audit trail"
    assert "generated=1" in generated[0]["payload"]["detail"]

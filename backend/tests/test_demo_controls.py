"""DEV-only demo bootstrap / reset endpoints for mock UI parity."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_demo_bootstrap_and_reset(
    client: TestClient, enrolled_student_headers: dict[str, str]
) -> None:
    boot = client.post("/api/v1/me/demo/bootstrap", headers=enrolled_student_headers)
    assert boot.status_code == 200, boot.text
    payload = boot.json()
    assert payload["subject_id"]
    assert payload["topic_id"]
    assert payload["topic_title"]
    assert (
        "overall topic quiz" in payload["message"].lower()
        or "unlocked" in payload["message"].lower()
    )

    directory = client.get("/api/v1/me/learning-directory", headers=enrolled_student_headers)
    assert directory.status_code == 200
    topic = directory.json()["subjects"][0]["topics"][0]
    assert topic["id"] == payload["topic_id"]
    assert topic["overall_quiz"]["unlocked"] is True
    for subtopic in topic["subtopics"]:
        assert subtopic["lesson_completed"] is True
        assert subtopic["quiz"]["passed"] is True

    reset = client.post("/api/v1/me/demo/reset", headers=enrolled_student_headers)
    assert reset.status_code == 200, reset.text
    assert reset.json()["status"] == "ok"

    after = client.get("/api/v1/me/learning-directory", headers=enrolled_student_headers)
    assert after.status_code == 200
    topic_after = after.json()["subjects"][0]["topics"][0]
    assert topic_after["overall_quiz"]["unlocked"] is False
    for subtopic in topic_after["subtopics"]:
        assert subtopic["lesson_completed"] is False
        assert subtopic["quiz"]["passed"] is False


def test_demo_bootstrap_requires_auth(client: TestClient) -> None:
    response = client.post("/api/v1/me/demo/bootstrap")
    assert response.status_code in {401, 403}

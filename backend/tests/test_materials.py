from uuid import UUID

from fastapi.testclient import TestClient


def test_list_materials(client: TestClient, enrolled_student_headers: dict[str, str]) -> None:
    response = client.get("/api/v1/materials", headers=enrolled_student_headers)
    assert response.status_code == 200
    topics = response.json()
    ids = {topic["id"] for topic in topics}
    assert "rectangles_squares_properties" in ids
    assert "square_numbers_patterns" in ids
    for topic in topics:
        assert topic["has_lesson"] is True
        assert topic["has_quiz"] is True
        assert topic["title"]


def test_get_lesson_includes_slides(
    client: TestClient, enrolled_student_headers: dict[str, str]
) -> None:
    response = client.get(
        "/api/v1/materials/rectangles_squares_properties", headers=enrolled_student_headers
    )
    assert response.status_code == 200
    payload = response.json()
    UUID(payload["id"])
    assert "Rectangles" in payload["title"]
    assert "## Slide 1" in payload["markdown"]
    assert len(payload["slides"]) >= 1
    assert payload["slides"][0]["number"] == 1
    assert payload["slides"][0]["title"]
    assert payload["slides"][0]["content"]


def test_get_quiz_strips_answer_key(
    client: TestClient, enrolled_student_headers: dict[str, str]
) -> None:
    response = client.get(
        "/api/v1/materials/square_numbers_patterns/quiz", headers=enrolled_student_headers
    )
    assert response.status_code == 200
    payload = response.json()
    UUID(payload["id"])
    assert len(payload["questions"]) == 10
    first = payload["questions"][0]
    assert first["number"] == 1
    assert first["difficulty"] == "Easy"
    assert len(first["options"]) == 4
    assert {option["label"] for option in first["options"]} == {"A", "B", "C", "D"}
    serialized = str(payload)
    assert "Answer Key" not in serialized
    assert "**B** —" not in serialized
    assert "1027 ends in 7" not in serialized
    assert "correct_option_label" not in serialized


def test_unknown_topic_returns_404(
    client: TestClient, enrolled_student_headers: dict[str, str]
) -> None:
    assert (
        client.get("/api/v1/materials/does_not_exist", headers=enrolled_student_headers).status_code
        == 404
    )
    assert (
        client.get(
            "/api/v1/materials/does_not_exist/quiz", headers=enrolled_student_headers
        ).status_code
        == 404
    )


def test_unenrolled_student_cannot_see_materials(client: TestClient) -> None:
    provision = client.post(
        "/api/v1/auth/provision-student",
        json={
            "email": "noenroll@example.com",
            "password": "password123",
            "full_name": "No Enroll",
            "student_identifier": "S-404",
        },
    )
    assert provision.status_code == 200
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "noenroll@example.com", "password": "password123"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    listed = client.get("/api/v1/materials", headers=headers)
    assert listed.status_code == 200
    assert listed.json() == []
    assert (
        client.get("/api/v1/materials/rectangles_squares_properties", headers=headers).status_code
        == 403
    )

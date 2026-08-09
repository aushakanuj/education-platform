from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from education_platform.modules.assessments.models import QuestionAnswerKey, QuizItem
from education_platform.modules.materials.seed import POC_INSTITUTION_NAME


def test_enrollments_after_poc_math(
    client: TestClient, enrolled_student_headers: dict[str, str]
) -> None:
    response = client.get("/api/v1/me/enrollments", headers=enrolled_student_headers)
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["grade_enrollments"]) == 1
    assert len(payload["subject_enrollments"]) == 1
    assert payload["subject_enrollments"][0]["subject_code"] == "MATH"


def test_quiz_attempt_scores_without_leaking_keys(
    client: TestClient,
    enrolled_student_headers: dict[str, str],
    seeded_db: Session,
) -> None:
    quiz = client.get(
        "/api/v1/materials/squares_cubes_roots/quiz", headers=enrolled_student_headers
    )
    assert quiz.status_code == 200
    questions = quiz.json()["questions"]

    start = client.post(
        "/api/v1/quizzes/squares_cubes_roots/attempts",
        headers=enrolled_student_headers,
    )
    assert start.status_code == 200
    attempt_id = start.json()["id"]
    assert start.json()["status"] == "in_progress"
    attempt_version_id = start.json()["quiz_version_id"]

    items = seeded_db.scalars(
        select(QuizItem)
        .where(QuizItem.quiz_version_id == UUID(str(attempt_version_id)))
        .order_by(QuizItem.sequence)
    ).all()
    assert items
    answers = []
    for item in items:
        key = seeded_db.scalar(
            select(QuestionAnswerKey).where(
                QuestionAnswerKey.question_version_id == item.question_version_id
            )
        )
        assert key is not None and key.correct_option_label is not None
        answers.append(
            {
                "question_number": item.sequence,
                "selected_option_label": key.correct_option_label,
            }
        )

    submit = client.post(
        f"/api/v1/attempts/{attempt_id}/submit",
        headers=enrolled_student_headers,
        json={"answers": answers},
    )
    assert submit.status_code == 200, submit.text
    result = submit.json()
    assert result["status"] == "scored"
    assert float(result["score_percent"]) == 100.0
    assert result["passed"] is True
    assert len(result["answers"]) == len(questions)
    serialized = str(result)
    assert "correct_option_label" not in serialized
    assert "Answer Key" not in serialized

    fetched = client.get(f"/api/v1/attempts/{attempt_id}", headers=enrolled_student_headers)
    assert fetched.status_code == 200
    assert fetched.json()["score_percent"] == result["score_percent"]

    again = client.post(
        f"/api/v1/attempts/{attempt_id}/submit",
        headers=enrolled_student_headers,
        json={"answers": answers},
    )
    assert again.status_code == 409


def test_unenrolled_cannot_start_attempt(client: TestClient) -> None:
    provision = client.post(
        "/api/v1/auth/provision-student",
        json={
            "email": "locked@example.com",
            "password": "password123",
            "full_name": "Locked",
            "student_identifier": "S-locked",
            "institution_name": POC_INSTITUTION_NAME,
        },
    )
    assert provision.status_code == 200
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "locked@example.com", "password": "password123"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    start = client.post("/api/v1/quizzes/quadrilaterals/attempts", headers=headers)
    assert start.status_code == 403

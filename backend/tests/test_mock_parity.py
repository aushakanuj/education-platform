"""Mock UI parity: learning directory, progress unlocks, resume, topic quiz."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from education_platform.modules.academics.models import Topic
from education_platform.modules.assessments.models import (
    CommonMasteryQuiz,
    QuestionAnswerKey,
    QuizItem,
    QuizResultReleaseMode,
    QuizScope,
    QuizVersion,
    QuizVersionStatus,
)
from education_platform.modules.materials.seed import seed_approved_materials


def _complete_lesson(client: TestClient, headers: dict[str, str], subtopic_id: str) -> None:
    response = client.put(
        f"/api/v1/subtopics/{subtopic_id}/material-progress",
        headers=headers,
        json={"status": "completed", "last_unit_ordinal": 1},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"


def _perfect_answers(seeded_db: Session, quiz_version_id: str) -> list[dict[str, object]]:
    items = seeded_db.scalars(
        select(QuizItem)
        .where(QuizItem.quiz_version_id == UUID(quiz_version_id))
        .order_by(QuizItem.sequence)
    ).all()
    answers: list[dict[str, object]] = []
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
    return answers


def test_learning_directory_hierarchy(
    client: TestClient, enrolled_student_headers: dict[str, str]
) -> None:
    response = client.get("/api/v1/me/learning-directory", headers=enrolled_student_headers)
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["subjects"]) == 1
    subject = payload["subjects"][0]
    assert subject["name"] == "Mathematics"
    assert subject["code"] == "MATH"
    assert len(subject["topics"]) == 1
    topic = subject["topics"][0]
    assert topic["slug"] == "approved_materials"
    assert "complete" in topic
    slugs = {subtopic["slug"] for subtopic in topic["subtopics"]}
    assert slugs == {"rectangles_squares_properties", "square_numbers_patterns"}
    assert topic["overall_quiz"] is not None
    assert topic["overall_quiz"]["scope"] == "topic_mastery"
    assert topic["overall_quiz"]["unlocked"] is False
    assert isinstance(topic["objectives"], list)
    assert len(topic["objectives"]) >= 2
    assert any(
        "square" in objective.lower() or "quadrilateral" in objective.lower()
        for objective in topic["objectives"]
    )
    for subtopic in topic["subtopics"]:
        assert subtopic["has_lesson"] is True
        assert subtopic["quiz"] is not None
        assert subtopic["quiz"]["unlocked"] is False
        assert subtopic["progress_percent"] == 0


def test_lesson_completion_unlocks_subtopic_quiz_and_restart(
    client: TestClient,
    enrolled_student_headers: dict[str, str],
    seeded_db: Session,
) -> None:
    directory = client.get("/api/v1/me/learning-directory", headers=enrolled_student_headers)
    subtopic = next(
        node
        for subject in directory.json()["subjects"]
        for topic in subject["topics"]
        for node in topic["subtopics"]
        if node["slug"] == "rectangles_squares_properties"
    )
    quiz_id = subtopic["quiz"]["id"]

    blocked = client.post(f"/api/v1/quizzes/{quiz_id}/attempts", headers=enrolled_student_headers)
    assert blocked.status_code == 403

    material = client.get(
        f"/api/v1/subtopics/{subtopic['id']}/material", headers=enrolled_student_headers
    )
    assert material.status_code == 200
    assert material.json()["quiz_unlocked"] is False

    _complete_lesson(client, enrolled_student_headers, subtopic["id"])
    material = client.get(
        f"/api/v1/subtopics/{subtopic['id']}/material", headers=enrolled_student_headers
    )
    assert material.json()["quiz_unlocked"] is True

    first = client.post(f"/api/v1/quizzes/{quiz_id}/attempts", headers=enrolled_student_headers)
    assert first.status_code == 200
    attempt_id = first.json()["id"]
    assert first.json()["questions"]
    second = client.post(f"/api/v1/quizzes/{quiz_id}/attempts", headers=enrolled_student_headers)
    assert second.status_code == 200
    assert second.json()["id"] != attempt_id
    assert second.json()["attempt_number"] == first.json()["attempt_number"]

    history = client.get(f"/api/v1/quizzes/{quiz_id}/attempts", headers=enrolled_student_headers)
    assert history.status_code == 200
    statuses = {row["id"]: row["status"] for row in history.json()}
    assert attempt_id not in statuses
    assert statuses[second.json()["id"]] == "in_progress"
    assert "abandoned" not in statuses.values()

    discarded = client.get(f"/api/v1/attempts/{attempt_id}", headers=enrolled_student_headers)
    assert discarded.status_code == 404


def test_topic_quiz_unlocks_after_subtopic_passes(
    client: TestClient,
    enrolled_student_headers: dict[str, str],
    seeded_db: Session,
) -> None:
    directory = client.get("/api/v1/me/learning-directory", headers=enrolled_student_headers)
    topic = directory.json()["subjects"][0]["topics"][0]
    overall_id = topic["overall_quiz"]["id"]

    blocked = client.post(
        f"/api/v1/quizzes/{overall_id}/attempts", headers=enrolled_student_headers
    )
    assert blocked.status_code == 403

    for subtopic in topic["subtopics"]:
        _complete_lesson(client, enrolled_student_headers, subtopic["id"])
        quiz_id = subtopic["quiz"]["id"]
        start = client.post(f"/api/v1/quizzes/{quiz_id}/attempts", headers=enrolled_student_headers)
        assert start.status_code == 200
        submit = client.post(
            f"/api/v1/attempts/{start.json()['id']}/submit",
            headers=enrolled_student_headers,
            json={"answers": _perfect_answers(seeded_db, start.json()["quiz_version_id"])},
        )
        assert submit.status_code == 200
        assert submit.json()["passed"] is True

    refreshed = client.get("/api/v1/me/learning-directory", headers=enrolled_student_headers)
    overall = refreshed.json()["subjects"][0]["topics"][0]["overall_quiz"]
    assert overall["unlocked"] is True

    start_overall = client.post(
        f"/api/v1/quizzes/{overall_id}/attempts", headers=enrolled_student_headers
    )
    assert start_overall.status_code == 200
    assert start_overall.json()["scope"] == "topic_mastery"
    assert len(start_overall.json()["questions"]) >= 1


def test_topic_quiz_stays_startable_after_subtopic_quiz_is_reversioned(
    client: TestClient,
    enrolled_student_headers: dict[str, str],
    seeded_db: Session,
) -> None:
    """A newer subtopic quiz version must not lock the topic quiz the directory still unlocks.

    Seed (and any later curriculum edit) mints a new released version without archiving the
    old one. The directory counts a pass on *any* version; start-attempt used to require a
    pass on the *latest* version, so students saw an unlocked overall quiz and then 403.
    """
    directory = client.get("/api/v1/me/learning-directory", headers=enrolled_student_headers)
    topic = directory.json()["subjects"][0]["topics"][0]
    overall_id = topic["overall_quiz"]["id"]

    for subtopic in topic["subtopics"]:
        _complete_lesson(client, enrolled_student_headers, subtopic["id"])
        quiz_id = subtopic["quiz"]["id"]
        start = client.post(f"/api/v1/quizzes/{quiz_id}/attempts", headers=enrolled_student_headers)
        assert start.status_code == 200
        submit = client.post(
            f"/api/v1/attempts/{start.json()['id']}/submit",
            headers=enrolled_student_headers,
            json={"answers": _perfect_answers(seeded_db, start.json()["quiz_version_id"])},
        )
        assert submit.status_code == 200
        assert submit.json()["passed"] is True

    first_quiz_id = UUID(str(topic["subtopics"][0]["quiz"]["id"]))
    current_max = seeded_db.scalar(
        select(QuizVersion.version_number)
        .where(QuizVersion.quiz_id == first_quiz_id)
        .order_by(QuizVersion.version_number.desc())
    )
    seeded_db.add(
        QuizVersion(
            quiz_id=first_quiz_id,
            version_number=int(current_max or 0) + 1,
            lifecycle_status=QuizVersionStatus.RELEASED,
            result_release_mode=QuizResultReleaseMode.IMMEDIATE,
            pass_threshold_percent=Decimal("70.00"),
            released_at=datetime.now(UTC),
        )
    )
    seeded_db.commit()

    refreshed = client.get("/api/v1/me/learning-directory", headers=enrolled_student_headers)
    overall = refreshed.json()["subjects"][0]["topics"][0]["overall_quiz"]
    assert overall["unlocked"] is True

    start_overall = client.post(
        f"/api/v1/quizzes/{overall_id}/attempts", headers=enrolled_student_headers
    )
    assert start_overall.status_code == 200, start_overall.text
    assert start_overall.json()["scope"] == "topic_mastery"


def test_immutable_reseed_preserves_attempts(
    client: TestClient,
    enrolled_student_headers: dict[str, str],
    seeded_db: Session,
) -> None:
    directory = client.get("/api/v1/me/learning-directory", headers=enrolled_student_headers)
    subtopic = directory.json()["subjects"][0]["topics"][0]["subtopics"][0]
    _complete_lesson(client, enrolled_student_headers, subtopic["id"])
    quiz_id = subtopic["quiz"]["id"]
    start = client.post(f"/api/v1/quizzes/{quiz_id}/attempts", headers=enrolled_student_headers)
    submit = client.post(
        f"/api/v1/attempts/{start.json()['id']}/submit",
        headers=enrolled_student_headers,
        json={"answers": _perfect_answers(seeded_db, start.json()["quiz_version_id"])},
    )
    assert submit.status_code == 200
    attempt_id = submit.json()["id"]

    seeded = seed_approved_materials(seeded_db, replace=False)
    assert seeded
    topic = seeded_db.scalar(select(Topic).where(Topic.slug == "approved_materials"))
    assert topic is not None
    overall = seeded_db.scalar(
        select(CommonMasteryQuiz).where(
            CommonMasteryQuiz.topic_id == topic.id,
            CommonMasteryQuiz.quiz_scope == QuizScope.TOPIC_MASTERY,
        )
    )
    assert overall is not None
    fetched = client.get(f"/api/v1/attempts/{attempt_id}", headers=enrolled_student_headers)
    assert fetched.status_code == 200
    assert fetched.json()["passed"] is True


def test_quiz_summary_lists_all_attempts_in_history(
    client: TestClient,
    enrolled_student_headers: dict[str, str],
    seeded_db: Session,
) -> None:
    directory = client.get("/api/v1/me/learning-directory", headers=enrolled_student_headers)
    subtopic = next(
        node
        for subject in directory.json()["subjects"]
        for topic in subject["topics"]
        for node in topic["subtopics"]
        if node["slug"] == "rectangles_squares_properties"
    )
    _complete_lesson(client, enrolled_student_headers, subtopic["id"])
    quiz_id = subtopic["quiz"]["id"]

    for _ in range(4):
        start = client.post(f"/api/v1/quizzes/{quiz_id}/attempts", headers=enrolled_student_headers)
        assert start.status_code == 200, start.text
        submit = client.post(
            f"/api/v1/attempts/{start.json()['id']}/submit",
            headers=enrolled_student_headers,
            json={"answers": _perfect_answers(seeded_db, start.json()["quiz_version_id"])},
        )
        assert submit.status_code == 200, submit.text

    refreshed = client.get("/api/v1/me/learning-directory", headers=enrolled_student_headers)
    quiz = next(
        node["quiz"]
        for subject in refreshed.json()["subjects"]
        for topic in subject["topics"]
        for node in topic["subtopics"]
        if node["slug"] == "rectangles_squares_properties"
    )
    assert quiz["attempt_count"] == 4
    assert len(quiz["recent_attempts"]) == 4


def test_submit_rejects_incomplete_answers(
    client: TestClient,
    enrolled_student_headers: dict[str, str],
) -> None:
    directory = client.get("/api/v1/me/learning-directory", headers=enrolled_student_headers)
    subtopic = next(
        node
        for subject in directory.json()["subjects"]
        for topic in subject["topics"]
        for node in topic["subtopics"]
        if node["slug"] == "square_numbers_patterns"
    )
    _complete_lesson(client, enrolled_student_headers, subtopic["id"])
    start = client.post(
        f"/api/v1/quizzes/{subtopic['quiz']['id']}/attempts",
        headers=enrolled_student_headers,
    )
    assert start.status_code == 200
    bad = client.post(
        f"/api/v1/attempts/{start.json()['id']}/submit",
        headers=enrolled_student_headers,
        json={"answers": [{"question_number": 1, "selected_option_label": "A"}]},
    )
    assert bad.status_code == 422

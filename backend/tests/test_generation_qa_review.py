"""Slice 2 QA review: same round machine on content, selective item/section repair."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_generation import SEEDED_SLUG
from test_generation_items import _accept_two_node_run
from test_generation_publish import _job, _reach_qa_review
from test_materials import (
    POC_INSTITUTION_NAME,
    POC_TEACHER_EMAIL,
    POC_TEACHER_PASSWORD,
    _assign_poc_teacher,
)

from education_platform.core.config import get_settings
from education_platform.modules.academics.models import Subtopic
from education_platform.modules.assessments import queries as assessment_queries
from education_platform.modules.assessments.models import QuizItem
from education_platform.modules.generation.items import (
    GeneratedItem,
    NodeItemRequest,
    items_from_chunks,
)
from education_platform.modules.generation.lesson import LessonSectionRequest, section_from_chunks
from education_platform.modules.generation.models import (
    ContentGenerationLessonSection,
    ContentGenerationRun,
    GenerationJob,
    GenerationRevision,
    ReviewRoundRow,
)
from education_platform.modules.generation.types import GenerationJobKind, ReviewStage, RunPhase
from education_platform.modules.generation.worker import process_generation_job_sync
from education_platform.modules.materials import service as materials_service


@pytest.fixture()
def admin_headers(client: TestClient) -> dict[str, str]:
    settings = get_settings()
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": settings.demo_admin_email,
            "password": settings.demo_admin_password,
            "institution_name": "POC Demo School",
        },
    )
    assert login.status_code == 200, login.text
    return {"Authorization": "Bearer " + login.json()["access_token"]}


@pytest.fixture()
def teacher_headers(client: TestClient, seeded_db: Session) -> dict[str, str]:
    _assign_poc_teacher(seeded_db)
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": POC_TEACHER_EMAIL,
            "password": POC_TEACHER_PASSWORD,
            "institution_name": POC_INSTITUTION_NAME,
        },
    )
    assert login.status_code == 200, login.text
    return {"Authorization": "Bearer " + login.json()["access_token"]}


@pytest.fixture()
def seeded_topic_id(seeded_db: Session) -> UUID:
    subtopic = seeded_db.scalar(select(Subtopic).where(Subtopic.slug == SEEDED_SLUG))
    assert subtopic is not None
    return subtopic.topic_id


def _items_from_request(request: NodeItemRequest) -> Sequence[GeneratedItem]:
    return items_from_chunks(request)


def _section_from_request(request: LessonSectionRequest) -> str:
    return section_from_chunks(request)


def _workspace(api: TestClient, headers: dict[str, str], run_id: UUID | str) -> dict[str, object]:
    response = api.get(f"/api/v1/teaching/generation-runs/{run_id}/review", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_qa_round_opens_after_both_jobs(
    client: TestClient,
    admin_headers: dict[str, str],
    seeded_topic_id: UUID,
    seeded_db: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_id = _reach_qa_review(
        client, admin_headers, seeded_topic_id, seeded_db, monkeypatch, tmp_path
    )
    workspace = _workspace(client, admin_headers, run_id)
    active = workspace["active_revision"]
    open_round = workspace["open_round"]
    assert isinstance(active, dict)
    assert isinstance(open_round, dict)
    assert active["stage"] == "qa"
    assert open_round["stage"] == "qa"
    assert open_round["number"] == 1
    snapshot = active["snapshot"]
    assert isinstance(snapshot, dict)
    sections = snapshot["lesson_sections"]
    items = snapshot["quiz_items"]
    assert isinstance(sections, list)
    assert isinstance(items, list)
    assert len(sections) == 2
    assert len(items) == 60
    assert all("correct_label" in item for item in items if isinstance(item, dict))
    seeded_db.expire_all()
    section_rows = list(
        seeded_db.scalars(
            select(ContentGenerationLessonSection).where(
                ContentGenerationLessonSection.run_id == run_id
            )
        ).all()
    )
    assert len(section_rows) == 2
    revision = seeded_db.scalar(
        select(GenerationRevision).where(
            GenerationRevision.run_id == run_id,
            GenerationRevision.stage == ReviewStage.QA,
            GenerationRevision.number == 1,
        )
    )
    assert revision is not None
    round_row = seeded_db.scalar(
        select(ReviewRoundRow).where(
            ReviewRoundRow.run_id == run_id, ReviewRoundRow.stage == ReviewStage.QA
        )
    )
    assert round_row is not None
    get_settings.cache_clear()


def test_teacher_item_and_section_change_requests(
    client: TestClient,
    admin_headers: dict[str, str],
    teacher_headers: dict[str, str],
    seeded_topic_id: UUID,
    seeded_db: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_id = _reach_qa_review(
        client, admin_headers, seeded_topic_id, seeded_db, monkeypatch, tmp_path
    )
    closer = _workspace(client, admin_headers, run_id)
    closer_round = closer["open_round"]
    closer_revision = closer["active_revision"]
    assert isinstance(closer_round, dict)
    assert isinstance(closer_revision, dict)
    admin_decision = client.post(
        f"/api/v1/teaching/generation-runs/{run_id}/review-rounds/{closer_round['id']}/decisions",
        headers=admin_headers,
        json={"revision_id": closer_revision["id"], "verdict": "approve"},
    )
    assert admin_decision.status_code == 403

    workspace = _workspace(client, teacher_headers, run_id)
    open_round = workspace["open_round"]
    active = workspace["active_revision"]
    assert isinstance(open_round, dict)
    assert isinstance(active, dict)
    snapshot = active["snapshot"]
    assert isinstance(snapshot, dict)
    sections = snapshot["lesson_sections"]
    items = snapshot["quiz_items"]
    assert isinstance(sections, list) and sections
    assert isinstance(items, list) and items
    section = sections[0]
    item = items[0]
    assert isinstance(section, dict)
    assert isinstance(item, dict)
    decided = client.post(
        f"/api/v1/teaching/generation-runs/{run_id}/review-rounds/{open_round['id']}/decisions",
        headers=teacher_headers,
        json={
            "revision_id": active["id"],
            "verdict": "changes_requested",
            "requests": [
                {
                    "target": {
                        "kind": "lesson_section",
                        "section_key": section["section_key"],
                    },
                    "field": "body",
                    "kind": "pedagogy",
                    "comment": "Add a worked example with unlike fractions.",
                },
                {
                    "target": {"kind": "quiz_item", "item_key": item["item_key"]},
                    "field": "prompt",
                    "kind": "assessment_validity",
                    "comment": "This stem is too vague for Grade 8.",
                },
            ],
        },
    )
    assert decided.status_code == 200, decided.text
    body = decided.json()
    assert body["verdict"] == "changes_requested"
    assert {row["target_kind"] for row in body["requests"]} == {"lesson_section", "quiz_item"}
    get_settings.cache_clear()


def test_selective_repair_does_not_wipe_bank_and_rewrite_cap(
    client: TestClient,
    admin_headers: dict[str, str],
    teacher_headers: dict[str, str],
    seeded_topic_id: UUID,
    seeded_db: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_id = _reach_qa_review(
        client, admin_headers, seeded_topic_id, seeded_db, monkeypatch, tmp_path
    )
    preview = client.get(f"/api/v1/teaching/generation-runs/{run_id}", headers=admin_headers).json()
    original_ids = [item["question_id"] for item in preview["qa_items"]]
    assert len(original_ids) == 60
    workspace = _workspace(client, teacher_headers, run_id)
    open_round = workspace["open_round"]
    active = workspace["active_revision"]
    assert isinstance(open_round, dict)
    assert isinstance(active, dict)
    snapshot = active["snapshot"]
    assert isinstance(snapshot, dict)
    items = snapshot["quiz_items"]
    sections = snapshot["lesson_sections"]
    assert isinstance(items, list) and items
    assert isinstance(sections, list) and sections
    target_item = items[0]
    target_section = sections[0]
    assert isinstance(target_item, dict)
    assert isinstance(target_section, dict)
    decided = client.post(
        f"/api/v1/teaching/generation-runs/{run_id}/review-rounds/{open_round['id']}/decisions",
        headers=teacher_headers,
        json={
            "revision_id": active["id"],
            "verdict": "changes_requested",
            "requests": [
                {
                    "target": {"kind": "quiz_item", "item_key": target_item["item_key"]},
                    "field": "whole_item",
                    "kind": "assessment_validity",
                    "comment": "Regenerate this item only.",
                },
                {
                    "target": {
                        "kind": "lesson_section",
                        "section_key": target_section["section_key"],
                    },
                    "field": "body",
                    "kind": "pedagogy",
                    "comment": "Clarify the recap.",
                },
            ],
        },
    )
    assert decided.status_code == 200, decided.text
    rewritten = client.post(
        f"/api/v1/teaching/generation-runs/{run_id}/review-rounds/{open_round['id']}/close",
        headers=admin_headers,
        json={"revision_id": active["id"], "action": "rewrite"},
    )
    assert rewritten.status_code == 200, rewritten.text
    assert rewritten.json()["kind"] == "rewrite_queued"
    seeded_db.expire_all()
    job = seeded_db.scalar(
        select(GenerationJob).where(
            GenerationJob.run_id == run_id,
            GenerationJob.kind == GenerationJobKind.REWRITE_CONTENT,
        )
    )
    assert job is not None
    process_generation_job_sync(
        job.id, write_items=_items_from_request, write_lesson=_section_from_request
    )
    seeded_db.expire_all()
    run = seeded_db.get(ContentGenerationRun, run_id)
    assert run is not None
    assert run.phase is RunPhase.QA_REVIEW
    quiz_items = list(
        seeded_db.scalars(
            select(QuizItem).where(QuizItem.quiz_version_id == run.draft_quiz_version_id)
        ).all()
    )
    assert len(quiz_items) == 60
    after = client.get(f"/api/v1/teaching/generation-runs/{run_id}", headers=admin_headers).json()
    after_ids = [item["question_id"] for item in after["qa_items"]]
    assert len(after_ids) == 60
    kept = set(original_ids) & set(after_ids)
    assert len(kept) >= 59
    assert target_item["item_key"] in after_ids

    round2 = _workspace(client, teacher_headers, run_id)
    open2 = round2["open_round"]
    active2 = round2["active_revision"]
    assert isinstance(open2, dict)
    assert isinstance(active2, dict)
    assert open2["number"] == 2
    assert active2["number"] == 2
    capped = client.post(
        f"/api/v1/teaching/generation-runs/{run_id}/review-rounds/{open2['id']}/close",
        headers=admin_headers,
        json={"revision_id": active2["id"], "action": "rewrite"},
    )
    assert capped.status_code == 409
    get_settings.cache_clear()


def test_qa_accept_current_does_not_publish(
    client: TestClient,
    admin_headers: dict[str, str],
    seeded_topic_id: UUID,
    seeded_db: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_id = _reach_qa_review(
        client, admin_headers, seeded_topic_id, seeded_db, monkeypatch, tmp_path
    )
    workspace = _workspace(client, admin_headers, run_id)
    open_round = workspace["open_round"]
    active = workspace["active_revision"]
    assert isinstance(open_round, dict)
    assert isinstance(active, dict)
    accepted = client.post(
        f"/api/v1/teaching/generation-runs/{run_id}/review-rounds/{open_round['id']}/close",
        headers=admin_headers,
        json={"revision_id": active["id"], "action": "accept_current"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["kind"] == "content_accepted"
    seeded_db.expire_all()
    run = seeded_db.get(ContentGenerationRun, run_id)
    assert run is not None
    assert run.phase is RunPhase.QA_REVIEW
    assert run.published_quiz_version_id is None
    assert run.published_lesson_version_id is None
    get_settings.cache_clear()


def test_qa_discard_and_publish_still_work(
    client: TestClient,
    admin_headers: dict[str, str],
    enrolled_student_headers: dict[str, str],
    seeded_topic_id: UUID,
    seeded_db: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    discard_id = _reach_qa_review(
        client, admin_headers, seeded_topic_id, seeded_db, monkeypatch, tmp_path
    )
    workspace = _workspace(client, admin_headers, discard_id)
    open_round = workspace["open_round"]
    active = workspace["active_revision"]
    assert isinstance(open_round, dict)
    assert isinstance(active, dict)
    discarded = client.post(
        f"/api/v1/teaching/generation-runs/{discard_id}/review-rounds/{open_round['id']}/close",
        headers=admin_headers,
        json={"revision_id": active["id"], "action": "discard", "rationale": "Wrong PDF."},
    )
    assert discarded.status_code == 200, discarded.text
    assert discarded.json()["kind"] == "run_discarded"
    seeded_db.expire_all()
    discarded_run = seeded_db.get(ContentGenerationRun, discard_id)
    assert discarded_run is not None
    assert discarded_run.phase is RunPhase.DISCARDED

    publish_id = _accept_two_node_run(client, admin_headers, seeded_topic_id, seeded_db)
    process_generation_job_sync(
        _job(seeded_db, publish_id, GenerationJobKind.ITEMS).id,
        write_items=_items_from_request,
    )
    process_generation_job_sync(
        _job(seeded_db, publish_id, GenerationJobKind.LESSON).id,
        write_lesson=_section_from_request,
    )
    published = client.post(
        f"/api/v1/teaching/generation-runs/{publish_id}/publish",
        headers=admin_headers,
    )
    assert published.status_code == 200, published.text
    material = client.get(
        f"/api/v1/topics/{seeded_topic_id}/material",
        headers=enrolled_student_headers,
    )
    assert material.status_code == 200, material.text
    assert "correct_label" not in material.text
    assert "correct_rationale" not in material.text
    get_settings.cache_clear()


def test_student_query_paths_still_have_no_keys() -> None:
    assert "QuestionAnswerKey" not in assessment_queries.__dict__
    assert "QuestionAnswerKey" not in materials_service.__dict__

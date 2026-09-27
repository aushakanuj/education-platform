"""Quiz items are enqueued only after the lesson exists."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_generation import SEEDED_SLUG
from test_generation_items import _accept_two_node_run, _silence_embed

from education_platform.core.config import get_settings
from education_platform.modules.academics.models import Subtopic
from education_platform.modules.generation.items import (
    GeneratedItem,
    NodeItemRequest,
    items_from_chunks,
)
from education_platform.modules.generation.lesson import section_from_chunks
from education_platform.modules.generation.models import ContentGenerationRun, GenerationJob
from education_platform.modules.generation.types import (
    GenerationJobKind,
    GenerationJobStatus,
    RunPhase,
)
from education_platform.modules.generation.worker import process_generation_job_sync


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
def seeded_topic_id(seeded_db: Session) -> UUID:
    subtopic = seeded_db.scalar(select(Subtopic).where(Subtopic.slug == SEEDED_SLUG))
    assert subtopic is not None
    return subtopic.topic_id


def _jobs(session: Session, run_id: UUID, kind: GenerationJobKind) -> list[GenerationJob]:
    return list(
        session.scalars(
            select(GenerationJob).where(
                GenerationJob.run_id == run_id,
                GenerationJob.kind == kind,
            )
        ).all()
    )


def test_accept_outline_enqueues_only_the_lesson(
    client: TestClient,
    admin_headers: dict[str, str],
    seeded_topic_id: UUID,
    seeded_db: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _silence_embed(monkeypatch, tmp_path)
    run_id = _accept_two_node_run(client, admin_headers, seeded_topic_id, seeded_db)
    body = client.get(f"/api/v1/teaching/generation-runs/{run_id}", headers=admin_headers).json()
    assert body["phase"] == "generating"
    assert {job["kind"] for job in body["jobs"]} == {"lesson"}
    seeded_db.expire_all()
    assert _jobs(seeded_db, run_id, GenerationJobKind.ITEMS) == []
    lessons = _jobs(seeded_db, run_id, GenerationJobKind.LESSON)
    assert len(lessons) == 1
    assert lessons[0].status is GenerationJobStatus.QUEUED
    get_settings.cache_clear()


def test_lesson_success_enqueues_items(
    client: TestClient,
    admin_headers: dict[str, str],
    seeded_topic_id: UUID,
    seeded_db: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _silence_embed(monkeypatch, tmp_path)
    run_id = _accept_two_node_run(client, admin_headers, seeded_topic_id, seeded_db)
    lesson = _jobs(seeded_db, run_id, GenerationJobKind.LESSON)[0]
    process_generation_job_sync(lesson.id, write_lesson=section_from_chunks)
    seeded_db.expire_all()
    run = seeded_db.get(ContentGenerationRun, run_id)
    assert run is not None
    assert run.draft_lesson_markdown
    assert run.phase is RunPhase.GENERATING
    items = _jobs(seeded_db, run_id, GenerationJobKind.ITEMS)
    assert len(items) == 1
    assert items[0].status is GenerationJobStatus.QUEUED
    get_settings.cache_clear()


def test_retry_after_lesson_succeeded_enqueues_only_items(
    client: TestClient,
    admin_headers: dict[str, str],
    seeded_topic_id: UUID,
    seeded_db: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _silence_embed(monkeypatch, tmp_path)
    run_id = _accept_two_node_run(client, admin_headers, seeded_topic_id, seeded_db)
    lesson = _jobs(seeded_db, run_id, GenerationJobKind.LESSON)[0]
    process_generation_job_sync(lesson.id, write_lesson=section_from_chunks)
    seeded_db.expire_all()

    def _explode(_request: NodeItemRequest) -> Sequence[GeneratedItem]:
        raise RuntimeError("items failed")

    items_job = _jobs(seeded_db, run_id, GenerationJobKind.ITEMS)[0]
    process_generation_job_sync(items_job.id, write_items=_explode)
    seeded_db.expire_all()
    failed = seeded_db.get(ContentGenerationRun, run_id)
    assert failed is not None
    assert failed.phase is RunPhase.FAILED

    retried = client.post(
        f"/api/v1/teaching/generation-runs/{run_id}/retry",
        headers=admin_headers,
    )
    assert retried.status_code == 200, retried.text
    assert {job["kind"] for job in retried.json()["jobs"]} == {"items"}
    seeded_db.expire_all()
    lessons = _jobs(seeded_db, run_id, GenerationJobKind.LESSON)
    assert len(lessons) == 1
    assert lessons[0].status is GenerationJobStatus.SUCCEEDED
    queued_items = [
        job
        for job in _jobs(seeded_db, run_id, GenerationJobKind.ITEMS)
        if job.status is GenerationJobStatus.QUEUED
    ]
    assert len(queued_items) == 1
    get_settings.cache_clear()


def test_items_job_with_empty_lesson_fails(
    client: TestClient,
    admin_headers: dict[str, str],
    seeded_topic_id: UUID,
    seeded_db: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _silence_embed(monkeypatch, tmp_path)
    run_id = _accept_two_node_run(client, admin_headers, seeded_topic_id, seeded_db)
    seeded_db.add(
        GenerationJob(
            run_id=run_id,
            kind=GenerationJobKind.ITEMS,
            status=GenerationJobStatus.QUEUED,
        )
    )
    seeded_db.commit()
    calls = {"n": 0}

    def _writer(request: NodeItemRequest) -> Sequence[GeneratedItem]:
        calls["n"] += 1
        return items_from_chunks(request)

    job = _jobs(seeded_db, run_id, GenerationJobKind.ITEMS)[0]
    process_generation_job_sync(job.id, write_items=_writer)
    seeded_db.expire_all()
    run = seeded_db.get(ContentGenerationRun, run_id)
    assert run is not None
    assert run.phase is RunPhase.FAILED
    assert run.failure_reason == "Cannot generate items before the lesson exists."
    assert calls["n"] == 0
    failed_job = seeded_db.get(GenerationJob, job.id)
    assert failed_job is not None
    assert failed_job.status is GenerationJobStatus.FAILED
    get_settings.cache_clear()

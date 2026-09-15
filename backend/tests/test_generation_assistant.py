"""Slice 3: generation-review assistant drafts a CR and cannot submit."""

from __future__ import annotations

import inspect
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from test_generation import (
    ADMIN,
    TEACHER,
    TEST_SPEC,
    _headers,
    _index_run,
    _outline_run,
    _silence_embed,
    _submit_admin,
    _write_one_node,
)

from education_platform.core.config import get_settings
from education_platform.db.url import to_sync_url
from education_platform.modules.academics.models import Subtopic
from education_platform.modules.assessments import queries as assessment_queries
from education_platform.modules.assistant.models import ChatConversation, ChatMessage
from education_platform.modules.assistant.strategy import AssistantKind, graph_for
from education_platform.modules.assistant.tools.registry import get_tool_registry
from education_platform.modules.generation.models import (
    GenerationChangeRequest,
    GenerationReviewMessage,
    ReviewDecisionRow,
)
from education_platform.modules.materials import service as materials_service
from education_platform.modules.synthetic.generator import generate_school

STUDENT = "student25@alnoor.school"


@pytest.fixture()
def alnoor(client: TestClient, clean_db: str) -> Iterator[TestClient]:
    engine = create_engine(to_sync_url(clean_db), pool_pre_ping=True)
    with Session(engine) as session:
        generate_school(session, TEST_SPEC)
        session.commit()
    engine.dispose()
    yield client


def _math_topic_id(api: TestClient, clean_db: str) -> UUID:
    listed = api.get("/api/v1/authoring/subtopics", headers=_headers(api, TEACHER))
    assert listed.status_code == 200, listed.text
    math = [row for row in listed.json() if row["subject"] == "Mathematics"]
    assert math
    engine = create_engine(to_sync_url(clean_db), pool_pre_ping=True)
    with Session(engine) as session:
        subtopic = session.get(Subtopic, UUID(math[0]["id"]))
        assert subtopic is not None
        topic_id = subtopic.topic_id
    engine.dispose()
    return topic_id


def _reach_outline_review(
    api: TestClient,
    admin_headers: dict[str, str],
    clean_db: str,
    topic_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> str:
    _silence_embed(monkeypatch, tmp_path)
    created = _submit_admin(api, admin_headers, topic_id)
    assert created.status_code == 202, created.text
    run_id = created.json()["run_id"]
    fetched = api.get(f"/api/v1/teaching/generation-runs/{run_id}", headers=admin_headers)
    intake_id = UUID(fetched.json()["intake_version_id"])
    engine = create_engine(to_sync_url(clean_db), pool_pre_ping=True)
    with Session(engine) as session:
        _index_run(session, intake_id)
        _outline_run(session, UUID(run_id), _write_one_node)
    engine.dispose()
    get_settings.cache_clear()
    return str(run_id)


def _workspace(api: TestClient, headers: dict[str, str], run_id: str) -> dict[str, Any]:
    response = api.get(f"/api/v1/teaching/generation-runs/{run_id}/review", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body


def test_graph_for_keeps_policy_and_generation_review_separate() -> None:
    policy = graph_for(AssistantKind.POLICY)
    review = graph_for(AssistantKind.GENERATION_REVIEW)
    assert policy.kind is AssistantKind.POLICY
    assert review.kind is AssistantKind.GENERATION_REVIEW
    assert type(policy) is not type(review)
    names = {spec.name for spec in get_tool_registry().list_specs()}
    assert "retrieve_chunks" in names
    assert "retrieve_run_chunks" not in names
    from education_platform.modules.assistant import generation_strategy as generation_mod

    source = inspect.getsource(generation_mod)
    assert "submit_teacher_decision" not in source
    assert "close_review_round" not in source
    assert "tools.retrieve_chunks" not in source
    assert "retrieve_run_chunks" in source
    assert "langgraph" not in source.lower()


def test_assistant_drafts_cr_without_submitting(
    alnoor: TestClient,
    clean_db: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    topic_id = _math_topic_id(alnoor, clean_db)
    admin_headers = _headers(alnoor, ADMIN)
    run_id = _reach_outline_review(alnoor, admin_headers, clean_db, topic_id, monkeypatch, tmp_path)
    teacher_headers = _headers(alnoor, TEACHER)
    workspace = _workspace(alnoor, teacher_headers, run_id)
    active = workspace["active_revision"]
    assert isinstance(active, dict)
    snapshot = active["snapshot"]
    assert isinstance(snapshot, dict)
    nodes = snapshot["nodes"]
    assert isinstance(nodes, list)
    node = nodes[0]
    assert isinstance(node, dict)

    retrieve_called = {"policy": False}

    async def _forbidden_retrieve(**kwargs: Any) -> dict[str, object]:
        del kwargs
        retrieve_called["policy"] = True
        raise AssertionError("policy retrieve_chunks must not run for generation review")

    with patch(
        "education_platform.modules.assistant.tools.retrieve_chunks.retrieve_chunks_handler",
        new=_forbidden_retrieve,
    ):
        posted = alnoor.post(
            f"/api/v1/teaching/generation-runs/{run_id}/assistant/turns",
            headers=teacher_headers,
            json={
                "revision_id": active["id"],
                "target": {"kind": "outline_node", "node_key": node["node_key"]},
                "message": "Draft a request that adds an outcome for variables on both sides.",
            },
        )
    assert posted.status_code == 200, posted.text
    body = posted.json()
    assert body["content"]
    draft = body["draft_change_request"]
    assert isinstance(draft, dict)
    assert draft["target"]["kind"] == "outline_node"
    assert draft["target"]["node_key"] == node["node_key"]
    assert draft["comment"]
    assert retrieve_called["policy"] is False

    engine = create_engine(to_sync_url(clean_db), pool_pre_ping=True)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ReviewDecisionRow)) == 0
        assert session.scalar(select(func.count()).select_from(GenerationChangeRequest)) == 0
        assert session.scalar(select(func.count()).select_from(ChatConversation)) == 0
        assert session.scalar(select(func.count()).select_from(ChatMessage)) == 0
        assert session.scalar(select(func.count()).select_from(GenerationReviewMessage)) == 2
    engine.dispose()

    after = _workspace(alnoor, teacher_headers, run_id)
    open_round = after["open_round"]
    assert isinstance(open_round, dict)
    assert after["request_threads"] == []

    submitted = alnoor.post(
        f"/api/v1/teaching/generation-runs/{run_id}/review-rounds/{open_round['id']}/decisions",
        headers=teacher_headers,
        json={
            "revision_id": active["id"],
            "verdict": "changes_requested",
            "requests": [draft],
        },
    )
    assert submitted.status_code == 200, submitted.text


def test_student_cannot_use_generation_assistant_or_see_keys(
    alnoor: TestClient,
    clean_db: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    topic_id = _math_topic_id(alnoor, clean_db)
    admin_headers = _headers(alnoor, ADMIN)
    run_id = _reach_outline_review(alnoor, admin_headers, clean_db, topic_id, monkeypatch, tmp_path)
    student_headers = _headers(alnoor, STUDENT)
    denied = alnoor.post(
        f"/api/v1/teaching/generation-runs/{run_id}/assistant/turns",
        headers=student_headers,
        json={
            "revision_id": "00000000-0000-0000-0000-000000000001",
            "message": "Draft a change request.",
        },
    )
    assert denied.status_code == 403
    assert "QuestionAnswerKey" not in assessment_queries.__dict__
    assert "QuestionAnswerKey" not in materials_service.__dict__


def test_policy_chats_and_text_to_sql_stay_separate(
    alnoor: TestClient,
    clean_db: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    topic_id = _math_topic_id(alnoor, clean_db)
    admin_headers = _headers(alnoor, ADMIN)
    teacher_headers = _headers(alnoor, TEACHER)
    run_id = _reach_outline_review(alnoor, admin_headers, clean_db, topic_id, monkeypatch, tmp_path)
    workspace = _workspace(alnoor, teacher_headers, run_id)
    active = workspace["active_revision"]
    assert isinstance(active, dict)

    drafted = alnoor.post(
        f"/api/v1/teaching/generation-runs/{run_id}/assistant/turns",
        headers=teacher_headers,
        json={
            "revision_id": active["id"],
            "message": "Explain why this node may be too broad and draft a request.",
        },
    )
    assert drafted.status_code == 200, drafted.text

    created = alnoor.post("/api/v1/chats", json={"title": "Attendance"}, headers=admin_headers)
    assert created.status_code == 201, created.text
    listed = alnoor.get("/api/v1/chats", headers=admin_headers)
    assert listed.status_code == 200
    assert any(row["id"] == created.json()["id"] for row in listed.json())
    assert all("draft_change_request" not in row for row in listed.json())

    sql_denied = alnoor.post(
        "/api/v1/text-to-sql/ask",
        headers=_headers(alnoor, STUDENT),
        json={"question": "how many students do I teach?"},
    )
    assert sql_denied.status_code == 403

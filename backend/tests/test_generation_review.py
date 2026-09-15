"""Slice 1 frozen-revision review: decisions, close, rewrite cap, accept still generates."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from test_generation import (
    ADMIN,
    SCHOOL,
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
from education_platform.modules.academics.models import Subtopic, TeachingAssignment, Topic
from education_platform.modules.assessments import queries as assessment_queries
from education_platform.modules.auth.models import RoleName, User, UserRole, UserStatus
from education_platform.modules.auth.security import hash_password
from education_platform.modules.generation.models import GenerationJob, ReviewDecisionRow
from education_platform.modules.generation.types import GenerationJobKind
from education_platform.modules.generation.worker import process_generation_job_sync
from education_platform.modules.materials import service as materials_service
from education_platform.modules.synthetic.generator import DEFAULT_PASSWORD, generate_school

SECOND_TEACHER = "second.teacher@alnoor.school"


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


def _workspace(api: TestClient, headers: dict[str, str], run_id: str) -> dict[str, object]:
    response = api.get(f"/api/v1/teaching/generation-runs/{run_id}/review", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_teacher_patch_is_410(
    alnoor: TestClient,
    clean_db: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    topic_id = _math_topic_id(alnoor, clean_db)
    admin_headers = _headers(alnoor, ADMIN)
    run_id = _reach_outline_review(alnoor, admin_headers, clean_db, topic_id, monkeypatch, tmp_path)
    teacher_headers = _headers(alnoor, TEACHER)
    body = alnoor.get(f"/api/v1/teaching/generation-runs/{run_id}", headers=teacher_headers).json()
    node = body["outline"]["nodes"][0]
    patched = alnoor.patch(
        f"/api/v1/teaching/generation-runs/{run_id}/outline",
        headers=teacher_headers,
        json={
            "nodes": [
                {
                    "id": node["id"],
                    "parent_id": None,
                    "slug": node["slug"],
                    "title": node["title"],
                    "weight": str(node["weight"]),
                    "matched_subtopic_id": node["matched_subtopic_id"],
                    "force_create": False,
                    "proposed_outcomes": node["proposed_outcomes"],
                    "sequence": node["sequence"],
                }
            ]
        },
    )
    assert patched.status_code == 410


def test_teacher_decision_200_and_close_403(
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
    open_round = workspace["open_round"]
    active = workspace["active_revision"]
    assert isinstance(open_round, dict)
    assert isinstance(active, dict)
    round_id = open_round["id"]
    revision_id = active["id"]
    snapshot = active["snapshot"]
    assert isinstance(snapshot, dict)
    nodes = snapshot["nodes"]
    assert isinstance(nodes, list)
    node = nodes[0]
    assert isinstance(node, dict)
    decided = alnoor.post(
        f"/api/v1/teaching/generation-runs/{run_id}/review-rounds/{round_id}/decisions",
        headers=teacher_headers,
        json={
            "revision_id": revision_id,
            "verdict": "changes_requested",
            "requests": [
                {
                    "target": {"kind": "outline_node", "node_key": node["node_key"]},
                    "field": "proposed_outcomes",
                    "kind": "curriculum_alignment",
                    "comment": "Add an outcome that checks both-sides equations.",
                }
            ],
        },
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["verdict"] == "changes_requested"
    closed = alnoor.post(
        f"/api/v1/teaching/generation-runs/{run_id}/review-rounds/{round_id}/close",
        headers=teacher_headers,
        json={"revision_id": revision_id, "action": "rewrite"},
    )
    assert closed.status_code == 403


def test_two_teachers_cannot_clobber(
    alnoor: TestClient,
    clean_db: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    topic_id = _math_topic_id(alnoor, clean_db)
    engine = create_engine(to_sync_url(clean_db), pool_pre_ping=True)
    with Session(engine) as session:
        topic = session.get(Topic, topic_id)
        assert topic is not None
        first = session.scalar(select(User).where(User.email == TEACHER))
        assert first is not None
        second = User(
            institution_id=first.institution_id,
            email=SECOND_TEACHER,
            full_name="Second Teacher",
            password_hash=hash_password(DEFAULT_PASSWORD),
            status=UserStatus.ACTIVE,
        )
        session.add(second)
        session.flush()
        session.add(UserRole(user_id=second.id, role=RoleName.TEACHER))
        assignment = session.scalar(
            select(TeachingAssignment).where(
                TeachingAssignment.teacher_user_id == first.id,
                TeachingAssignment.grade_subject_offering_id == topic.grade_subject_offering_id,
            )
        )
        assert assignment is not None
        session.add(
            TeachingAssignment(
                teacher_user_id=second.id,
                academic_period_id=assignment.academic_period_id,
                grade_subject_offering_id=topic.grade_subject_offering_id,
                section_id=assignment.section_id,
                status=assignment.status,
            )
        )
        session.commit()
    engine.dispose()

    admin_headers = _headers(alnoor, ADMIN)
    run_id = _reach_outline_review(alnoor, admin_headers, clean_db, topic_id, monkeypatch, tmp_path)
    first_headers = _headers(alnoor, TEACHER)
    second_headers = _headers(alnoor, SECOND_TEACHER, SCHOOL)
    workspace = _workspace(alnoor, first_headers, run_id)
    open_round = workspace["open_round"]
    active = workspace["active_revision"]
    assert isinstance(open_round, dict)
    assert isinstance(active, dict)
    round_id = str(open_round["id"])
    revision_id = active["id"]
    snapshot = active["snapshot"]
    assert isinstance(snapshot, dict)
    nodes = snapshot["nodes"]
    assert isinstance(nodes, list)
    node = nodes[0]
    assert isinstance(node, dict)
    first_decision = alnoor.post(
        f"/api/v1/teaching/generation-runs/{run_id}/review-rounds/{round_id}/decisions",
        headers=first_headers,
        json={"revision_id": revision_id, "verdict": "approve"},
    )
    assert first_decision.status_code == 200, first_decision.text
    second_decision = alnoor.post(
        f"/api/v1/teaching/generation-runs/{run_id}/review-rounds/{round_id}/decisions",
        headers=second_headers,
        json={
            "revision_id": revision_id,
            "verdict": "changes_requested",
            "requests": [
                {
                    "target": {"kind": "outline_node", "node_key": node["node_key"]},
                    "field": "title",
                    "kind": "pedagogy",
                    "comment": "Rename this heading for Grade 8.",
                }
            ],
        },
    )
    assert second_decision.status_code == 200, second_decision.text
    duplicate = alnoor.post(
        f"/api/v1/teaching/generation-runs/{run_id}/review-rounds/{round_id}/decisions",
        headers=first_headers,
        json={"revision_id": revision_id, "verdict": "approve"},
    )
    assert duplicate.status_code == 409
    engine = create_engine(to_sync_url(clean_db), pool_pre_ping=True)
    with Session(engine) as session:
        rows = list(
            session.scalars(
                select(ReviewDecisionRow).where(ReviewDecisionRow.round_id == UUID(round_id))
            ).all()
        )
        assert len(rows) == 2
        assert {row.verdict for row in rows} == {"approve", "changes_requested"}
    engine.dispose()


def test_rewrite_cap_and_accept_still_generates(
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
    open_round = workspace["open_round"]
    active = workspace["active_revision"]
    assert isinstance(open_round, dict)
    assert isinstance(active, dict)
    round_id = open_round["id"]
    revision_id = active["id"]
    snapshot = active["snapshot"]
    assert isinstance(snapshot, dict)
    nodes = snapshot["nodes"]
    assert isinstance(nodes, list)
    node = nodes[0]
    assert isinstance(node, dict)
    decided = alnoor.post(
        f"/api/v1/teaching/generation-runs/{run_id}/review-rounds/{round_id}/decisions",
        headers=teacher_headers,
        json={
            "revision_id": revision_id,
            "verdict": "changes_requested",
            "requests": [
                {
                    "target": {"kind": "outline_node", "node_key": node["node_key"]},
                    "field": "title",
                    "kind": "structure",
                    "comment": "Make the heading more specific.",
                }
            ],
        },
    )
    assert decided.status_code == 200, decided.text
    rewritten = alnoor.post(
        f"/api/v1/teaching/generation-runs/{run_id}/review-rounds/{round_id}/close",
        headers=admin_headers,
        json={"revision_id": revision_id, "action": "rewrite"},
    )
    assert rewritten.status_code == 200, rewritten.text
    assert rewritten.json()["kind"] == "rewrite_queued"
    engine = create_engine(to_sync_url(clean_db), pool_pre_ping=True)
    with Session(engine) as session:
        job = session.scalar(
            select(GenerationJob).where(
                GenerationJob.run_id == UUID(run_id),
                GenerationJob.kind == GenerationJobKind.REWRITE_OUTLINE,
            )
        )
        assert job is not None
        process_generation_job_sync(job.id)
        session.expire_all()
    engine.dispose()

    round2 = _workspace(alnoor, teacher_headers, run_id)
    open2 = round2["open_round"]
    active2 = round2["active_revision"]
    assert isinstance(open2, dict)
    assert isinstance(active2, dict)
    assert open2["number"] == 2
    round2_id = open2["id"]
    revision2_id = active2["id"]
    capped = alnoor.post(
        f"/api/v1/teaching/generation-runs/{run_id}/review-rounds/{round2_id}/close",
        headers=admin_headers,
        json={"revision_id": revision2_id, "action": "rewrite"},
    )
    assert capped.status_code == 409

    accepted = alnoor.post(
        f"/api/v1/teaching/generation-runs/{run_id}/review-rounds/{round2_id}/close",
        headers=admin_headers,
        json={"revision_id": revision2_id, "action": "accept_current"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["kind"] == "outline_accepted"
    run = alnoor.get(f"/api/v1/teaching/generation-runs/{run_id}", headers=admin_headers)
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["phase"] == "generating"
    kinds = {job["kind"] for job in body["jobs"]}
    assert kinds == {"items", "lesson"}
    assert all(node["quota"] is not None for node in body["outline"]["nodes"])
    assert all(node["accepted_subtopic_id"] for node in body["outline"]["nodes"])
    get_settings.cache_clear()


def test_override_and_accept_still_generates(
    alnoor: TestClient,
    clean_db: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    topic_id = _math_topic_id(alnoor, clean_db)
    admin_headers = _headers(alnoor, ADMIN)
    run_id = _reach_outline_review(alnoor, admin_headers, clean_db, topic_id, monkeypatch, tmp_path)
    workspace = _workspace(alnoor, admin_headers, run_id)
    open_round = workspace["open_round"]
    active = workspace["active_revision"]
    assert isinstance(open_round, dict)
    assert isinstance(active, dict)
    snapshot = active["snapshot"]
    assert isinstance(snapshot, dict)
    nodes = snapshot["nodes"]
    assert isinstance(nodes, list)
    node = nodes[0]
    assert isinstance(node, dict)
    replacement = {
        "target_item_count": snapshot["target_item_count"],
        "nodes": [
            {
                **node,
                "title": "Fractions for Grade 8",
            }
        ],
    }
    overridden = alnoor.post(
        f"/api/v1/teaching/generation-runs/{run_id}/review-rounds/{open_round['id']}/close",
        headers=admin_headers,
        json={
            "revision_id": active["id"],
            "action": "override_and_accept",
            "rationale": "Keep one node and freeze it for this offering.",
            "replacement": replacement,
        },
    )
    assert overridden.status_code == 200, overridden.text
    assert overridden.json()["kind"] == "outline_accepted"
    run = alnoor.get(f"/api/v1/teaching/generation-runs/{run_id}", headers=admin_headers)
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["phase"] == "generating"
    kinds = {job["kind"] for job in body["jobs"]}
    assert kinds == {"items", "lesson"}
    assert body["outline"]["nodes"][0]["title"] == "Fractions for Grade 8"
    assert all(node["quota"] is not None for node in body["outline"]["nodes"])
    assert all(node["accepted_subtopic_id"] for node in body["outline"]["nodes"])
    get_settings.cache_clear()


def test_student_query_paths_still_have_no_keys() -> None:
    assert "QuestionAnswerKey" not in assessment_queries.__dict__
    assert "QuestionAnswerKey" not in materials_service.__dict__

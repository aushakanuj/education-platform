"""Slice 3 lesson generation: sequential sections, stitch, draft markdown, qa_review."""

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
from education_platform.modules.generation.adk import KATEX_MARKDOWN_RULES
from education_platform.modules.generation.items import (
    GeneratedItem,
    NodeItemRequest,
    items_from_chunks,
)
from education_platform.modules.generation.lesson import (
    _SECTION_SYSTEM,
    _STITCH_SYSTEM,
    LessonSection,
    LessonSectionRequest,
    SectionPass,
    StitchRequest,
    assert_usable_mermaid,
    parse_mermaid_diagram,
    section_from_chunks,
    stitch_sections,
    write_topic_lesson,
)
from education_platform.modules.generation.models import ContentGenerationRun, GenerationJob
from education_platform.modules.generation.types import (
    GenerationJobKind,
    GenerationJobStatus,
    RunPhase,
)
from education_platform.modules.generation.worker import process_generation_job_sync
from education_platform.modules.materials.models import SourceMaterial


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


def _items_from_request(request: NodeItemRequest) -> Sequence[GeneratedItem]:
    return items_from_chunks(request)


def _section_from_request(request: LessonSectionRequest) -> str:
    return section_from_chunks(request)


def _job(session: Session, run_id: UUID, kind: GenerationJobKind) -> GenerationJob:
    job = session.scalar(
        select(GenerationJob).where(GenerationJob.run_id == run_id, GenerationJob.kind == kind)
    )
    assert job is not None
    return job


def test_mermaid_parse_rejects_invalid() -> None:
    parse_mermaid_diagram("flowchart TD\n  A[Idea] --> B[Try]")
    with pytest.raises(ValueError, match="empty"):
        parse_mermaid_diagram("  ")
    with pytest.raises(ValueError, match="unrecognized"):
        parse_mermaid_diagram("not a diagram")
    with pytest.raises(ValueError, match="unbalanced"):
        parse_mermaid_diagram("flowchart TD\n  A[Idea")


def test_lesson_system_prompt_requires_renderable_katex() -> None:
    assert KATEX_MARKDOWN_RULES in _SECTION_SYSTEM
    assert "$2x + 3 = 11$" in KATEX_MARKDOWN_RULES
    assert r"\frac{2x}{2} = 6" in KATEX_MARKDOWN_RULES
    assert r"\(" in KATEX_MARKDOWN_RULES
    assert r"\\(" in KATEX_MARKDOWN_RULES
    assert r"\\frac" in KATEX_MARKDOWN_RULES
    assert "```markdown" in KATEX_MARKDOWN_RULES
    assert "```json" in KATEX_MARKDOWN_RULES
    assert "$x $" in KATEX_MARKDOWN_RULES
    assert "$...$" in _STITCH_SYSTEM
    assert r"\(" in _STITCH_SYSTEM


def test_write_topic_lesson_is_sequential_not_a_dump() -> None:
    captured: list[LessonSectionRequest] = []

    def _capture(request: LessonSectionRequest) -> str:
        captured.append(request)
        return section_from_chunks(request)

    first = LessonSectionRequest(
        heading="Properties of squares",
        objectives=("Identify properties of squares",),
        chunk_texts=("A square has four equal sides.",),
        grade_voice="Write for Grade 6 students studying Shapes.",
        glossary=(),
        prior_titles=(),
        defined_terms=(),
        prior_recap="",
    )
    second = LessonSectionRequest(
        heading="Angles of a triangle",
        objectives=("State the angle sum",),
        chunk_texts=("Interior angles sum to 180 degrees.",),
        grade_voice=first.grade_voice,
        glossary=(),
        prior_titles=(),
        defined_terms=(),
        prior_recap="",
    )
    markdown = write_topic_lesson((first, second), write_section=_capture)
    assert len(captured) == 2
    assert captured[0].heading == "Properties of squares"
    assert captured[1].heading == "Angles of a triangle"
    assert captured[0].prior_titles == ()
    assert "Properties of squares" in captured[1].prior_titles
    assert "180" not in "".join(captured[0].chunk_texts)
    assert "equal sides" not in "".join(captured[1].chunk_texts)
    assert "four equal sides" in markdown
    assert "180 degrees" in markdown
    assert "**Topic recap.**" in markdown
    assert markdown.index("Properties of squares") < markdown.index("Angles of a triangle")
    assert_usable_mermaid(markdown)


def test_overflow_splits_idea_then_examples() -> None:
    captured: list[LessonSectionRequest] = []

    def _capture(request: LessonSectionRequest) -> str:
        captured.append(request)
        return section_from_chunks(request)

    long_a = "alpha excerpt " + ("nines " * 1200)
    long_b = "beta excerpt " + ("eights " * 1200)
    request = LessonSectionRequest(
        heading="Long section",
        objectives=("Keep the idea",),
        chunk_texts=(long_a, long_b),
        grade_voice="Write for Grade 6 students.",
        glossary=(),
        prior_titles=(),
        defined_terms=(),
        prior_recap="",
    )
    markdown = write_topic_lesson((request,), write_section=_capture)
    assert [item.pass_kind for item in captured] == [SectionPass.IDEA, SectionPass.EXAMPLES]
    assert "nines" in captured[0].chunk_texts[0]
    assert "eights" in captured[1].chunk_texts[0]
    assert "Long section" in markdown


def test_mermaid_retry_on_parser_error() -> None:
    calls = {"count": 0}

    def _flaky(request: LessonSectionRequest) -> str:
        calls["count"] += 1
        if calls["count"] == 1:
            return f"## {request.heading}\n```mermaid\nnot a diagram\n```\n"
        return section_from_chunks(request)

    request = LessonSectionRequest(
        heading="Squares",
        objectives=("Identify squares",),
        chunk_texts=("A square has four equal sides.",),
        grade_voice="Write for Grade 6 students.",
        glossary=(),
        prior_titles=(),
        defined_terms=(),
        prior_recap="",
    )
    markdown = write_topic_lesson((request,), write_section=_flaky)
    assert calls["count"] == 2
    assert_usable_mermaid(markdown)


def test_stitch_does_not_rewrite_teaching() -> None:
    section_md = section_from_chunks(
        LessonSectionRequest(
            heading="Squares",
            objectives=("Identify squares",),
            chunk_texts=("A square has four equal sides.",),
            grade_voice="Write for Grade 6 students.",
            glossary=(),
            prior_titles=(),
            defined_terms=(),
            prior_recap="",
        )
    )
    stitched = stitch_sections(
        StitchRequest(
            grade_voice="Write for Grade 6 students.",
            sections=(
                LessonSection(
                    heading="Squares",
                    markdown=section_md,
                    recap="Squares",
                    defined_terms=("Squares",),
                ),
            ),
        )
    )
    assert section_md.strip() in stitched
    assert "**Topic recap.**" in stitched


def test_items_only_success_stays_generating(
    client: TestClient,
    admin_headers: dict[str, str],
    seeded_topic_id: UUID,
    seeded_db: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _silence_embed(monkeypatch, tmp_path)
    run_id = _accept_two_node_run(client, admin_headers, seeded_topic_id, seeded_db)
    process_generation_job_sync(
        _job(seeded_db, run_id, GenerationJobKind.ITEMS).id,
        write_items=_items_from_request,
    )
    seeded_db.expire_all()
    run = seeded_db.get(ContentGenerationRun, run_id)
    assert run is not None
    assert run.phase is RunPhase.GENERATING
    assert run.draft_lesson_markdown is None
    lesson = _job(seeded_db, run_id, GenerationJobKind.LESSON)
    assert lesson.status is GenerationJobStatus.QUEUED
    get_settings.cache_clear()


def test_lesson_worker_is_per_node_and_does_not_publish(
    client: TestClient,
    admin_headers: dict[str, str],
    enrolled_student_headers: dict[str, str],
    seeded_topic_id: UUID,
    seeded_db: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _silence_embed(monkeypatch, tmp_path)
    run_id = _accept_two_node_run(client, admin_headers, seeded_topic_id, seeded_db)
    captured: list[LessonSectionRequest] = []

    def _capture(request: LessonSectionRequest) -> str:
        captured.append(request)
        return section_from_chunks(request)

    process_generation_job_sync(
        _job(seeded_db, run_id, GenerationJobKind.LESSON).id,
        write_lesson=_capture,
    )
    seeded_db.expire_all()
    run = seeded_db.get(ContentGenerationRun, run_id)
    assert run is not None
    assert run.phase is RunPhase.GENERATING
    assert run.draft_lesson_markdown is not None
    assert "four equal sides" in run.draft_lesson_markdown.lower()
    assert "180" in run.draft_lesson_markdown
    assert "**Topic recap.**" in run.draft_lesson_markdown
    assert len(captured) == 2
    assert "180" not in "".join(captured[0].chunk_texts)
    assert "equal sides" not in "".join(captured[1].chunk_texts).lower()
    topic_lessons = list(
        seeded_db.scalars(
            select(SourceMaterial).where(
                SourceMaterial.topic_id == seeded_topic_id,
                SourceMaterial.slug == "lesson",
            )
        ).all()
    )
    assert topic_lessons == []
    subtopic = seeded_db.scalar(select(Subtopic).where(Subtopic.slug == SEEDED_SLUG))
    assert subtopic is not None
    student = client.get(
        f"/api/v1/subtopics/{subtopic.id}/material",
        headers=enrolled_student_headers,
    )
    assert student.status_code == 200, student.text
    get_settings.cache_clear()


def test_both_jobs_advance_to_qa_review(
    client: TestClient,
    admin_headers: dict[str, str],
    seeded_topic_id: UUID,
    seeded_db: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _silence_embed(monkeypatch, tmp_path)
    run_id = _accept_two_node_run(client, admin_headers, seeded_topic_id, seeded_db)
    process_generation_job_sync(
        _job(seeded_db, run_id, GenerationJobKind.ITEMS).id,
        write_items=_items_from_request,
    )
    seeded_db.expire_all()
    run = seeded_db.get(ContentGenerationRun, run_id)
    assert run is not None
    assert run.phase is RunPhase.GENERATING
    process_generation_job_sync(
        _job(seeded_db, run_id, GenerationJobKind.LESSON).id,
        write_lesson=_section_from_request,
    )
    seeded_db.expire_all()
    run = seeded_db.get(ContentGenerationRun, run_id)
    assert run is not None
    assert run.phase is RunPhase.QA_REVIEW
    assert run.draft_lesson_markdown
    assert run.draft_quiz_version_id is not None
    assert run.published_lesson_version_id is None
    assert run.published_quiz_version_id is None
    body = client.get(f"/api/v1/teaching/generation-runs/{run_id}", headers=admin_headers).json()
    assert body["phase"] == "qa_review"
    assert body["draft_lesson_markdown"]
    get_settings.cache_clear()


def test_lesson_then_items_also_reaches_qa_review(
    client: TestClient,
    admin_headers: dict[str, str],
    seeded_topic_id: UUID,
    seeded_db: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _silence_embed(monkeypatch, tmp_path)
    run_id = _accept_two_node_run(client, admin_headers, seeded_topic_id, seeded_db)
    process_generation_job_sync(
        _job(seeded_db, run_id, GenerationJobKind.LESSON).id,
        write_lesson=_section_from_request,
    )
    seeded_db.expire_all()
    run = seeded_db.get(ContentGenerationRun, run_id)
    assert run is not None
    assert run.phase is RunPhase.GENERATING
    process_generation_job_sync(
        _job(seeded_db, run_id, GenerationJobKind.ITEMS).id,
        write_items=_items_from_request,
    )
    seeded_db.expire_all()
    run = seeded_db.get(ContentGenerationRun, run_id)
    assert run is not None
    assert run.phase is RunPhase.QA_REVIEW
    get_settings.cache_clear()


def test_lesson_retry_does_not_duplicate_markdown(
    client: TestClient,
    admin_headers: dict[str, str],
    seeded_topic_id: UUID,
    seeded_db: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _silence_embed(monkeypatch, tmp_path)
    run_id = _accept_two_node_run(client, admin_headers, seeded_topic_id, seeded_db)
    process_generation_job_sync(
        _job(seeded_db, run_id, GenerationJobKind.ITEMS).id,
        write_items=_items_from_request,
    )
    calls = {"count": 0}

    def _fail_first(request: LessonSectionRequest) -> str:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("LLM down on first section")
        return section_from_chunks(request)

    process_generation_job_sync(
        _job(seeded_db, run_id, GenerationJobKind.LESSON).id,
        write_lesson=_fail_first,
    )
    seeded_db.expire_all()
    run = seeded_db.get(ContentGenerationRun, run_id)
    assert run is not None
    assert run.phase is RunPhase.FAILED
    assert run.draft_lesson_markdown is None

    retried = client.post(
        f"/api/v1/teaching/generation-runs/{run_id}/retry",
        headers=admin_headers,
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["phase"] == "generating"
    queued = seeded_db.scalar(
        select(GenerationJob).where(
            GenerationJob.run_id == run_id,
            GenerationJob.kind == GenerationJobKind.LESSON,
            GenerationJob.status == GenerationJobStatus.QUEUED,
        )
    )
    assert queued is not None
    process_generation_job_sync(queued.id, write_lesson=_section_from_request)
    seeded_db.expire_all()
    run = seeded_db.get(ContentGenerationRun, run_id)
    assert run is not None
    assert run.phase is RunPhase.QA_REVIEW
    assert run.draft_lesson_markdown is not None
    assert run.draft_lesson_markdown.count("**Topic recap.**") == 1
    lesson_jobs = list(
        seeded_db.scalars(
            select(GenerationJob).where(
                GenerationJob.run_id == run_id,
                GenerationJob.kind == GenerationJobKind.LESSON,
            )
        ).all()
    )
    assert len(lesson_jobs) == 2
    get_settings.cache_clear()

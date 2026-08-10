"""Admin RAG ingest API and worker unit tests."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from education_platform.core.config import get_settings
from education_platform.modules.academics.models import Subtopic
from education_platform.modules.materials.models import (
    SourceChunk,
    SourceMaterialVersion,
    SourceMaterialVersionStatus,
)
from education_platform.modules.rag.chunking import chunk_text
from education_platform.modules.rag.models import (
    IngestJob,
    IngestJobStatus,
    IngestTargetKind,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    KnowledgeDocumentVersionStatus,
)
from education_platform.modules.rag.vector_store import (
    VectorRow,
    count_for_version,
    delete_by_version,
    upsert_rows,
)
from education_platform.workers.ingest import process_ingest_job_sync

TINY_PDF = (
    b"%PDF-1.1\n"
    b"1 0 obj<<>>endobj\n"
    b"2 0 obj<< /Length 44 >>stream\n"
    b"BT /F1 12 Tf 100 700 Td (Hello RAG) Tj ET\n"
    b"endstream\nendobj\n"
    b"3 0 obj<< /Type /Page /Parent 4 0 R /Contents 2 0 R >>endobj\n"
    b"4 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n"
    b"5 0 obj<< /Type /Catalog /Pages 4 0 R >>endobj\n"
    b"xref\n0 6\n0000000000 65535 f \n"
    b"trailer<< /Size 6 /Root 5 0 R >>\nstartxref\n0\n%%EOF\n"
)


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
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.fixture()
def seeded_subtopic_id(seeded_db: Session) -> UUID:
    subtopic = seeded_db.scalar(
        select(Subtopic).where(Subtopic.slug == "rectangles_squares_properties")
    )
    assert subtopic is not None
    return subtopic.id


async def _fake_enqueue(ingest_job_id: UUID) -> str:
    return f"job-{ingest_job_id}"


def test_student_forbidden_on_curriculum_upload(
    client: TestClient,
    enrolled_student_headers: dict[str, str],
    seeded_subtopic_id: UUID,
) -> None:
    response = client.post(
        f"/api/v1/admin/subtopics/{seeded_subtopic_id}/materials",
        headers=enrolled_student_headers,
        data={"title": "Lesson PDF"},
        files={"file": ("lesson.pdf", TINY_PDF, "application/pdf")},
    )
    assert response.status_code == 403


def test_student_forbidden_on_knowledge_upload(
    client: TestClient,
    enrolled_student_headers: dict[str, str],
) -> None:
    response = client.post(
        "/api/v1/admin/knowledge-documents",
        headers=enrolled_student_headers,
        data={"title": "Handbook", "doc_type": "handbook"},
        files={"file": ("handbook.pdf", TINY_PDF, "application/pdf")},
    )
    assert response.status_code == 403


def test_admin_curriculum_upload_enqueues(
    client: TestClient,
    admin_headers: dict[str, str],
    seeded_subtopic_id: UUID,
    seeded_db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "education_platform.modules.rag.service.enqueue_ingest_job",
        _fake_enqueue,
    )
    response = client.post(
        f"/api/v1/admin/subtopics/{seeded_subtopic_id}/materials",
        headers=admin_headers,
        data={"title": "Geometry PDF"},
        files={"file": ("lesson.pdf", TINY_PDF, "application/pdf")},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["lifecycle_status"] == "processing"
    assert body["version_number"] >= 1
    version_id = UUID(body["version_id"])

    seeded_db.expire_all()
    version = seeded_db.get(SourceMaterialVersion, version_id)
    assert version is not None
    assert version.lifecycle_status == SourceMaterialVersionStatus.PROCESSING
    assert version.blob_object_key
    blob_path = get_settings().upload_dir / version.blob_object_key
    assert blob_path.is_file()

    job = seeded_db.get(IngestJob, UUID(body["ingest_job_id"]))
    assert job is not None
    assert job.target_kind == IngestTargetKind.SOURCE_MATERIAL_VERSION
    assert job.redis_job_id == f"job-{job.id}"

    status = client.get(
        f"/api/v1/admin/material-versions/{version_id}",
        headers=admin_headers,
    )
    assert status.status_code == 200
    assert status.json()["lifecycle_status"] == "processing"
    assert status.json()["chunk_count"] == 0


def test_admin_knowledge_upload_and_list(
    client: TestClient,
    admin_headers: dict[str, str],
    seeded_db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "education_platform.modules.rag.service.enqueue_ingest_job",
        _fake_enqueue,
    )
    response = client.post(
        "/api/v1/admin/knowledge-documents",
        headers=admin_headers,
        data={
            "title": "Attendance Policy",
            "doc_type": "policy",
            "required_roles": '["administrator","teacher"]',
        },
        files={"file": ("policy.pdf", TINY_PDF, "application/pdf")},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    document_id = UUID(body["document_id"])
    version_id = UUID(body["version_id"])

    listed = client.get("/api/v1/admin/knowledge-documents", headers=admin_headers)
    assert listed.status_code == 200
    assert any(item["id"] == str(document_id) for item in listed.json())

    detail = client.get(
        f"/api/v1/admin/knowledge-documents/{document_id}",
        headers=admin_headers,
    )
    assert detail.status_code == 200
    assert detail.json()["versions"][0]["id"] == str(version_id)

    status = client.get(
        f"/api/v1/admin/knowledge-document-versions/{version_id}",
        headers=admin_headers,
    )
    assert status.status_code == 200
    assert status.json()["lifecycle_status"] == "processing"

    seeded_db.expire_all()
    document = seeded_db.get(KnowledgeDocument, document_id)
    assert document is not None
    assert document.doc_type == "policy"


def test_upload_returns_503_when_queue_down(
    client: TestClient,
    admin_headers: dict[str, str],
    seeded_subtopic_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _boom(_ingest_job_id: UUID) -> str:
        raise ConnectionError("redis down")

    monkeypatch.setattr(
        "education_platform.modules.rag.service.enqueue_ingest_job",
        _boom,
    )
    response = client.post(
        f"/api/v1/admin/subtopics/{seeded_subtopic_id}/materials",
        headers=admin_headers,
        data={"title": "Geometry PDF"},
        files={"file": ("lesson.pdf", TINY_PDF, "application/pdf")},
    )
    assert response.status_code == 503
    assert "queue" in response.json()["detail"].lower()


def test_chunk_text_dedupes_and_overlaps() -> None:
    words = " ".join(f"word{i}" for i in range(50))
    chunks = chunk_text(words, chunk_tokens=20, overlap_ratio=0.15)
    assert len(chunks) >= 2
    assert chunks[0].ordinal == 1
    assert chunks[0].content_hash
    assert len({c.content_hash for c in chunks}) == len(chunks)


def test_sqlite_vec_upsert_and_delete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vector_path = tmp_path / "vec.db"
    monkeypatch.setenv("VECTOR_DB_PATH", str(vector_path))
    get_settings.cache_clear()

    version_id = uuid4()
    chunk_id = uuid4()
    embedding = [0.01] * 384
    upsert_rows(
        [
            VectorRow(
                chunk_id=chunk_id,
                embedding=embedding,
                doc_id=uuid4(),
                doc_kind="knowledge_document",
                institution_id=uuid4(),
                required_roles=["administrator"],
                doc_type="policy",
                page_number=1,
                version_id=version_id,
            )
        ],
        path=vector_path,
    )
    assert count_for_version(version_id, path=vector_path) == 1
    assert delete_by_version(version_id, path=vector_path) == 1
    assert count_for_version(version_id, path=vector_path) == 0
    get_settings.cache_clear()


def test_worker_happy_path_source_material(
    seeded_db: Session,
    seeded_subtopic_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from education_platform.modules.materials.models import SourceMaterial
    from education_platform.modules.rag import storage

    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "vectors.db"))
    get_settings.cache_clear()

    monkeypatch.setattr(
        "education_platform.workers.ingest.embed_texts",
        lambda texts: [[0.02] * 384 for _ in texts],
    )

    material = SourceMaterial(
        subtopic_id=seeded_subtopic_id,
        title="Upload lesson",
        slug="upload-lesson",
    )
    seeded_db.add(material)
    seeded_db.flush()
    object_key = storage.build_object_key(
        institution_id=uuid4(),
        kind="source_materials",
        filename="lesson.pdf",
    )
    storage.store_bytes(object_key, TINY_PDF)
    version = SourceMaterialVersion(
        source_material_id=material.id,
        version_number=1,
        lifecycle_status=SourceMaterialVersionStatus.PROCESSING,
        title="Upload lesson",
        content_format="pdf",
        blob_object_key=object_key,
        blob_content_type="application/pdf",
        checksum=storage.sha256_hex(TINY_PDF),
    )
    seeded_db.add(version)
    seeded_db.flush()
    job = IngestJob(
        target_kind=IngestTargetKind.SOURCE_MATERIAL_VERSION,
        target_id=version.id,
        status=IngestJobStatus.QUEUED,
    )
    seeded_db.add(job)
    seeded_db.commit()

    process_ingest_job_sync(
        str(job.id),
        extract_text=lambda _path: "A square has four equal sides. " * 40,
    )

    seeded_db.expire_all()
    refreshed = seeded_db.get(SourceMaterialVersion, version.id)
    assert refreshed is not None
    assert refreshed.lifecycle_status == SourceMaterialVersionStatus.READY
    chunks = seeded_db.scalars(
        select(SourceChunk).where(SourceChunk.source_material_version_id == version.id)
    ).all()
    assert len(chunks) >= 1
    done = seeded_db.get(IngestJob, job.id)
    assert done is not None
    assert done.status == IngestJobStatus.SUCCEEDED
    get_settings.cache_clear()


def test_worker_failed_parse_marks_failed(
    seeded_db: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from education_platform.modules.rag import storage

    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "vectors.db"))
    get_settings.cache_clear()

    document = KnowledgeDocument(
        institution_id=_institution_id(seeded_db),
        title="Broken Policy",
        slug=f"broken-{uuid4().hex[:8]}",
        doc_type="policy",
        required_roles=["administrator"],
    )
    seeded_db.add(document)
    seeded_db.flush()
    object_key = storage.build_object_key(
        institution_id=document.institution_id,
        kind="knowledge_documents",
        filename="bad.pdf",
    )
    storage.store_bytes(object_key, TINY_PDF)
    version = KnowledgeDocumentVersion(
        document_id=document.id,
        version_number=1,
        lifecycle_status=KnowledgeDocumentVersionStatus.PROCESSING,
        blob_object_key=object_key,
        blob_content_type="application/pdf",
        checksum=storage.sha256_hex(TINY_PDF),
    )
    seeded_db.add(version)
    seeded_db.flush()
    job = IngestJob(
        target_kind=IngestTargetKind.KNOWLEDGE_DOCUMENT_VERSION,
        target_id=version.id,
        status=IngestJobStatus.QUEUED,
    )
    seeded_db.add(job)
    seeded_db.commit()

    def _boom(_path: Path) -> str:
        raise RuntimeError("Docling parse failed")

    process_ingest_job_sync(str(job.id), extract_text=_boom)

    seeded_db.expire_all()
    refreshed = seeded_db.get(KnowledgeDocumentVersion, version.id)
    assert refreshed is not None
    assert refreshed.lifecycle_status == KnowledgeDocumentVersionStatus.FAILED
    assert refreshed.failure_reason
    assert "Docling" in refreshed.failure_reason
    done = seeded_db.get(IngestJob, job.id)
    assert done is not None
    assert done.status == IngestJobStatus.FAILED
    assert (
        seeded_db.scalars(
            select(KnowledgeChunk).where(KnowledgeChunk.knowledge_document_version_id == version.id)
        ).all()
        == []
    )
    get_settings.cache_clear()


def _institution_id(session: Session) -> UUID:
    from education_platform.modules.auth.models import Institution

    institution = session.scalar(select(Institution).limit(1))
    assert institution is not None
    return institution.id

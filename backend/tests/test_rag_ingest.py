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
from education_platform.modules.rag.chunking import (
    SECTION_HEADING_MAX_LEN,
    TextChunk,
    _page_number_from_meta,
    _section_heading_from_meta,
    chunk_docling_document,
    content_hash,
)
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
    search_similar,
    upsert_rows,
)
from education_platform.workers.ingest import process_ingest_job_sync
from education_platform.workers.runner import claim_next_job, poll_once

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

SAMPLE_SECTION = "Properties of squares"
SAMPLE_CHUNK_TEXT = f"{SAMPLE_SECTION}\nA square has four equal sides and four right angles."


def _sample_chunks(*, text: str = SAMPLE_CHUNK_TEXT) -> list[TextChunk]:
    digest = content_hash(text)
    return [
        TextChunk(
            ordinal=1,
            text=text,
            content_hash=digest,
            token_count=len(text.split()),
            page_number=1,
            section_heading=SAMPLE_SECTION,
        )
    ]


class _StubProv:
    def __init__(self, page_no: int) -> None:
        self.page_no = page_no


class _StubDocItem:
    def __init__(self, *page_nos: int) -> None:
        self.prov = [_StubProv(n) for n in page_nos]


class _StubMeta:
    def __init__(
        self,
        *,
        headings: list[str] | None = None,
        doc_items: list[_StubDocItem] | None = None,
    ) -> None:
        self.headings = headings
        self.doc_items = doc_items or []


class _StubChunk:
    def __init__(self, text: str, meta: _StubMeta) -> None:
        self.text = text
        self.meta = meta


class _StubChunker:
    def __init__(self, chunks: list[_StubChunk]) -> None:
        self._chunks = chunks

    def chunk(self, dl_doc: object, **_kwargs: object) -> list[_StubChunk]:
        _ = dl_doc
        return list(self._chunks)

    def contextualize(self, chunk: _StubChunk) -> str:
        headings = chunk.meta.headings or []
        if headings:
            return "\n".join([*headings, chunk.text])
        return chunk.text


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
) -> None:
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
    assert job.status == IngestJobStatus.QUEUED

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
) -> None:
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
    job = seeded_db.get(IngestJob, UUID(body["ingest_job_id"]))
    assert job is not None
    assert job.status == IngestJobStatus.QUEUED


def test_page_number_from_meta_uses_first_provenance() -> None:
    meta = _StubMeta(doc_items=[_StubDocItem(2, 3), _StubDocItem(1)])
    assert _page_number_from_meta(meta) == 2
    assert _page_number_from_meta(_StubMeta()) is None


def test_section_heading_from_meta_joins_and_clips() -> None:
    meta = _StubMeta(headings=["Chapter 1", "Properties of squares"])
    assert _section_heading_from_meta(meta) == "Chapter 1 > Properties of squares"

    long_heading = "A" * (SECTION_HEADING_MAX_LEN + 40)
    clipped = _section_heading_from_meta(_StubMeta(headings=[long_heading]))
    assert clipped is not None
    assert len(clipped) == SECTION_HEADING_MAX_LEN
    assert _section_heading_from_meta(_StubMeta(headings=None)) is None


def test_chunk_docling_document_preserves_tables_and_dedupes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table_md = "| col | value |\n| --- | --- |\n| a | 1 |"
    stub_chunks = [
        _StubChunk(table_md, _StubMeta(headings=["Tables"], doc_items=[_StubDocItem(1)])),
        _StubChunk(table_md, _StubMeta(headings=["Tables"], doc_items=[_StubDocItem(1)])),
        _StubChunk("Unique prose", _StubMeta(headings=["Prose"], doc_items=[_StubDocItem(2)])),
    ]

    class _FakeHybridChunker:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self._inner = _StubChunker(stub_chunks)

        def chunk(self, dl_doc: object, **kwargs: object) -> list[_StubChunk]:
            return self._inner.chunk(dl_doc, **kwargs)

        def contextualize(self, chunk: _StubChunk) -> str:
            return self._inner.contextualize(chunk)

    class _FakeTokenizer:
        def count_tokens(self, text: str) -> int:
            return len(text.split())

        def get_max_tokens(self) -> int:
            return 256

    monkeypatch.setattr(
        "docling_core.transforms.chunker.hybrid_chunker.HybridChunker",
        _FakeHybridChunker,
    )
    monkeypatch.setattr(
        "docling_core.transforms.chunker.tokenizer.huggingface.HuggingFaceTokenizer",
        lambda **_kwargs: _FakeTokenizer(),
    )
    monkeypatch.setattr(
        "transformers.AutoTokenizer.from_pretrained",
        lambda *_args, **_kwargs: object(),
    )

    chunks = chunk_docling_document(document=object())
    assert len(chunks) == 2
    assert "| col | value |" in chunks[0].text
    assert "\n" in chunks[0].text
    assert chunks[0].page_number == 1
    assert chunks[0].section_heading == "Tables"
    assert chunks[1].ordinal == 2
    assert chunks[1].page_number == 2
    assert len({c.content_hash for c in chunks}) == 2


def test_pgvector_upsert_delete_and_search(clean_db: str) -> None:
    _ = clean_db
    get_settings.cache_clear()

    version_id = uuid4()
    chunk_id = uuid4()
    institution_id = uuid4()
    embedding = [0.01] * 384
    upsert_rows(
        [
            VectorRow(
                chunk_id=chunk_id,
                embedding=embedding,
                doc_id=uuid4(),
                doc_kind="knowledge_document",
                institution_id=institution_id,
                required_roles=["administrator"],
                doc_type="policy",
                page_number=1,
                version_id=version_id,
            )
        ]
    )
    assert count_for_version(version_id) == 1
    hits = search_similar(
        embedding,
        institution_id=institution_id,
        limit=5,
        required_role="administrator",
        doc_kind="knowledge_document",
        doc_type="policy",
    )
    assert len(hits) == 1
    assert hits[0].chunk_id == chunk_id
    assert delete_by_version(version_id) == 1
    assert count_for_version(version_id) == 0
    get_settings.cache_clear()


def test_claim_loop_processes_queued_job(
    seeded_db: Session,
    seeded_subtopic_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from education_platform.modules.materials.models import SourceMaterial
    from education_platform.modules.rag import storage

    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    monkeypatch.setattr(
        "education_platform.workers.ingest.embed_texts",
        lambda texts: [[0.03] * 384 for _ in texts],
    )

    material = SourceMaterial(
        subtopic_id=seeded_subtopic_id,
        title="Claim loop lesson",
        slug=f"claim-loop-{uuid4().hex[:8]}",
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
        title="Claim loop lesson",
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

    claimed = claim_next_job(seeded_db)
    assert claimed == job.id
    seeded_db.expire_all()
    running = seeded_db.get(IngestJob, job.id)
    assert running is not None
    assert running.status == IngestJobStatus.RUNNING

    process_ingest_job_sync(
        str(job.id),
        parse_pdf=lambda _path: _sample_chunks(),
    )

    seeded_db.expire_all()
    done = seeded_db.get(IngestJob, job.id)
    assert done is not None
    assert done.status == IngestJobStatus.SUCCEEDED
    refreshed = seeded_db.get(SourceMaterialVersion, version.id)
    assert refreshed is not None
    assert refreshed.lifecycle_status == SourceMaterialVersionStatus.READY
    assert count_for_version(version.id) >= 1

    assert poll_once(session=seeded_db) is None
    get_settings.cache_clear()


def test_idle_poll_reuses_shared_sync_engine(
    seeded_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The worker loop must not create a new SQLAlchemy engine on every poll.

    Previously ``_sync_session`` called ``create_engine`` per iteration and only
    closed the Session, leaking connection pools until Postgres refused new
    clients.
    """
    from sqlalchemy import create_engine as real_create_engine

    from education_platform.db.session import get_sync_engine, reset_engine

    _ = seeded_db
    reset_engine()
    engine = get_sync_engine()
    created: list[object] = []

    def _counting_create_engine(*args: object, **kwargs: object) -> object:
        created.append(object())
        return real_create_engine(*args, **kwargs)

    monkeypatch.setattr("education_platform.db.session.create_engine", _counting_create_engine)
    assert poll_once() is None
    assert poll_once() is None
    assert poll_once() is None
    assert get_sync_engine() is engine
    assert created == []
    reset_engine()
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
        parse_pdf=lambda _path: _sample_chunks(),
    )

    seeded_db.expire_all()
    refreshed = seeded_db.get(SourceMaterialVersion, version.id)
    assert refreshed is not None
    assert refreshed.lifecycle_status == SourceMaterialVersionStatus.READY
    chunks = seeded_db.scalars(
        select(SourceChunk).where(SourceChunk.source_material_version_id == version.id)
    ).all()
    assert len(chunks) == 1
    assert chunks[0].page_number == 1
    assert chunks[0].section_heading == SAMPLE_SECTION
    done = seeded_db.get(IngestJob, job.id)
    assert done is not None
    assert done.status == IngestJobStatus.SUCCEEDED
    assert count_for_version(version.id) >= 1
    get_settings.cache_clear()


def test_worker_happy_path_knowledge_document(
    seeded_db: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from education_platform.modules.rag import storage

    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    monkeypatch.setattr(
        "education_platform.workers.ingest.embed_texts",
        lambda texts: [[0.04] * 384 for _ in texts],
    )

    document = KnowledgeDocument(
        institution_id=_institution_id(seeded_db),
        title="Handbook",
        slug=f"handbook-{uuid4().hex[:8]}",
        doc_type="handbook",
        required_roles=["administrator", "teacher"],
    )
    seeded_db.add(document)
    seeded_db.flush()
    object_key = storage.build_object_key(
        institution_id=document.institution_id,
        kind="knowledge_documents",
        filename="handbook.pdf",
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

    process_ingest_job_sync(
        str(job.id),
        parse_pdf=lambda _path: _sample_chunks(),
    )

    seeded_db.expire_all()
    refreshed = seeded_db.get(KnowledgeDocumentVersion, version.id)
    assert refreshed is not None
    assert refreshed.lifecycle_status == KnowledgeDocumentVersionStatus.READY
    chunks = seeded_db.scalars(
        select(KnowledgeChunk).where(KnowledgeChunk.knowledge_document_version_id == version.id)
    ).all()
    assert len(chunks) == 1
    assert chunks[0].page_number == 1
    assert chunks[0].section_heading == SAMPLE_SECTION
    done = seeded_db.get(IngestJob, job.id)
    assert done is not None
    assert done.status == IngestJobStatus.SUCCEEDED
    assert count_for_version(version.id) >= 1
    get_settings.cache_clear()


def test_worker_failed_parse_marks_failed(
    seeded_db: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from education_platform.modules.rag import storage

    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
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

    def _boom(_path: Path) -> list[TextChunk]:
        raise RuntimeError("Docling parse failed")

    process_ingest_job_sync(str(job.id), parse_pdf=_boom)

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

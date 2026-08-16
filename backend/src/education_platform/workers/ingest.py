"""Ingest worker: parse → chunk → embed → index uploaded PDFs."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from education_platform.db.session import sync_session
from education_platform.modules.academics.models import (
    AcademicPeriod,
    GradeSubjectOffering,
    PeriodGrade,
    Subtopic,
    Topic,
)
from education_platform.modules.materials.models import (
    SourceChunk,
    SourceMaterial,
    SourceMaterialVersion,
    SourceMaterialVersionStatus,
)
from education_platform.modules.rag import storage
from education_platform.modules.rag.chunking import TextChunk, chunk_docling_document
from education_platform.modules.rag.contracts import IngestJobClaim
from education_platform.modules.rag.embeddings import embed_texts
from education_platform.modules.rag.models import (
    IngestJob,
    IngestJobStatus,
    IngestTargetKind,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    KnowledgeDocumentVersionStatus,
)
from education_platform.modules.rag.vector_store import VectorRow, delete_by_version, upsert_rows

logger = logging.getLogger(__name__)

ParsePdfFn = Callable[[Path], list[TextChunk]]


def convert_pdf_with_docling(path: Path) -> Any:
    """Convert a PDF to a DoclingDocument (lazy import; keeps layout structure)."""
    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    result = converter.convert(str(path))
    return result.document


def parse_pdf_with_docling(path: Path) -> list[TextChunk]:
    """Parse a PDF with Docling and chunk via HybridChunker."""
    document = convert_pdf_with_docling(path)
    return chunk_docling_document(document)


def _sync_session() -> Session:
    return sync_session()


def _fail_job(session: Session, job: IngestJob, reason: str) -> None:
    job.status = IngestJobStatus.FAILED
    job.error = reason
    session.commit()


def _mark_source_failed(session: Session, version: SourceMaterialVersion, reason: str) -> None:
    version.lifecycle_status = SourceMaterialVersionStatus.FAILED
    version.failure_reason = reason


def _mark_knowledge_failed(
    session: Session, version: KnowledgeDocumentVersion, reason: str
) -> None:
    version.lifecycle_status = KnowledgeDocumentVersionStatus.FAILED
    version.failure_reason = reason


def _persist_and_embed(
    *,
    session: Session,
    chunks: list[TextChunk],
    version_id: UUID,
    doc_id: UUID,
    doc_kind: str,
    institution_id: UUID,
    required_roles: list[str],
    doc_type: str | None,
    create_chunk: Callable[[TextChunk], Any],
    clear_existing: Callable[[], None],
) -> None:
    clear_existing()
    session.flush()
    delete_by_version(version_id)

    orm_chunks: list[Any] = []
    for chunk in chunks:
        row = create_chunk(chunk)
        session.add(row)
        orm_chunks.append(row)
    session.flush()

    embeddings = embed_texts([c.text for c in chunks])
    vector_rows = [
        VectorRow(
            chunk_id=orm.id,
            embedding=embedding,
            doc_id=doc_id,
            doc_kind=doc_kind,
            institution_id=institution_id,
            required_roles=required_roles,
            doc_type=doc_type,
            page_number=chunk.page_number,
            version_id=version_id,
        )
        for orm, embedding, chunk in zip(orm_chunks, embeddings, chunks, strict=True)
    ]
    upsert_rows(vector_rows)


def process_ingest_job_sync(
    ingest_job_id: str,
    *,
    parse_pdf: ParsePdfFn | None = None,
) -> None:
    parse = parse_pdf or parse_pdf_with_docling
    session = _sync_session()
    try:
        job = session.get(IngestJob, UUID(ingest_job_id))
        if job is None:
            logger.error("Ingest job %s not found", ingest_job_id)
            return

        try:
            claim = IngestJobClaim.model_validate(job)
        except ValidationError as exc:
            logger.error("Ingest job %s failed claim validation: %s", ingest_job_id, exc)
            job.status = IngestJobStatus.FAILED
            job.error = f"Invalid ingest job claim: {exc}"[:2000]
            session.commit()
            return

        job.status = IngestJobStatus.RUNNING
        session.commit()

        try:
            if claim.target_kind == IngestTargetKind.SOURCE_MATERIAL_VERSION:
                _process_source_material(session, job, parse)
            elif claim.target_kind == IngestTargetKind.KNOWLEDGE_DOCUMENT_VERSION:
                _process_knowledge_document(session, job, parse)
            else:
                _fail_job(session, job, f"Unknown target kind: {claim.target_kind}")
        except Exception as exc:
            logger.exception("Ingest job %s failed", ingest_job_id)
            session.rollback()
            job = session.get(IngestJob, UUID(ingest_job_id))
            if job is None:
                return
            reason = str(exc)[:2000]
            if job.target_kind == IngestTargetKind.SOURCE_MATERIAL_VERSION:
                version = session.get(SourceMaterialVersion, job.target_id)
                if version is not None:
                    _mark_source_failed(session, version, reason)
            elif job.target_kind == IngestTargetKind.KNOWLEDGE_DOCUMENT_VERSION:
                version_k = session.get(KnowledgeDocumentVersion, job.target_id)
                if version_k is not None:
                    _mark_knowledge_failed(session, version_k, reason)
            job.status = IngestJobStatus.FAILED
            job.error = reason
            session.commit()
    finally:
        session.close()


def _process_source_material(session: Session, job: IngestJob, parse: ParsePdfFn) -> None:
    version = session.get(SourceMaterialVersion, job.target_id)
    if version is None:
        _fail_job(session, job, "Source material version not found")
        return

    version.lifecycle_status = SourceMaterialVersionStatus.PROCESSING
    version.failure_reason = None
    session.commit()

    if not version.blob_object_key:
        _mark_source_failed(session, version, "Missing blob object key")
        _fail_job(session, job, "Missing blob object key")
        return

    path = storage.resolve_blob_path(version.blob_object_key)
    chunks = parse(path)
    if not chunks:
        _mark_source_failed(session, version, "No extractable text")
        _fail_job(session, job, "No extractable text")
        return

    material = session.get(SourceMaterial, version.source_material_id)
    if material is None:
        _mark_source_failed(session, version, "Source material missing")
        _fail_job(session, job, "Source material missing")
        return

    institution_id = session.scalar(
        select(AcademicPeriod.institution_id)
        .select_from(Subtopic)
        .join(Topic, Topic.id == Subtopic.topic_id)
        .join(GradeSubjectOffering, GradeSubjectOffering.id == Topic.grade_subject_offering_id)
        .join(PeriodGrade, PeriodGrade.id == GradeSubjectOffering.period_grade_id)
        .join(AcademicPeriod, AcademicPeriod.id == PeriodGrade.academic_period_id)
        .where(Subtopic.id == material.subtopic_id)
    )
    if institution_id is None:
        _mark_source_failed(session, version, "Unable to resolve institution")
        _fail_job(session, job, "Unable to resolve institution")
        return

    def clear_existing() -> None:
        session.execute(
            delete(SourceChunk).where(SourceChunk.source_material_version_id == version.id)
        )

    def create_chunk(chunk: TextChunk) -> SourceChunk:
        return SourceChunk(
            source_material_version_id=version.id,
            ordinal=chunk.ordinal,
            text=chunk.text,
            content_hash=chunk.content_hash,
            page_number=chunk.page_number,
            section_heading=chunk.section_heading,
            token_count=chunk.token_count,
        )

    _persist_and_embed(
        session=session,
        chunks=chunks,
        version_id=version.id,
        doc_id=material.id,
        doc_kind="source_material",
        institution_id=institution_id,
        required_roles=["student", "teacher", "administrator"],
        doc_type="curriculum",
        create_chunk=create_chunk,
        clear_existing=clear_existing,
    )
    version.lifecycle_status = SourceMaterialVersionStatus.READY
    version.failure_reason = None
    job.status = IngestJobStatus.SUCCEEDED
    job.error = None
    session.commit()


def _process_knowledge_document(session: Session, job: IngestJob, parse: ParsePdfFn) -> None:
    version = session.get(KnowledgeDocumentVersion, job.target_id)
    if version is None:
        _fail_job(session, job, "Knowledge document version not found")
        return

    version.lifecycle_status = KnowledgeDocumentVersionStatus.PROCESSING
    version.failure_reason = None
    session.commit()

    if not version.blob_object_key:
        _mark_knowledge_failed(session, version, "Missing blob object key")
        _fail_job(session, job, "Missing blob object key")
        return

    path = storage.resolve_blob_path(version.blob_object_key)
    chunks = parse(path)
    if not chunks:
        _mark_knowledge_failed(session, version, "No extractable text")
        _fail_job(session, job, "No extractable text")
        return

    document = session.get(KnowledgeDocument, version.document_id)
    if document is None:
        _mark_knowledge_failed(session, version, "Knowledge document missing")
        _fail_job(session, job, "Knowledge document missing")
        return

    roles = [str(r) for r in (document.required_roles or ["administrator", "teacher"])]

    def clear_existing() -> None:
        session.execute(
            delete(KnowledgeChunk).where(KnowledgeChunk.knowledge_document_version_id == version.id)
        )

    def create_chunk(chunk: TextChunk) -> KnowledgeChunk:
        return KnowledgeChunk(
            knowledge_document_version_id=version.id,
            ordinal=chunk.ordinal,
            text=chunk.text,
            content_hash=chunk.content_hash,
            page_number=chunk.page_number,
            section_heading=chunk.section_heading,
            token_count=chunk.token_count,
        )

    _persist_and_embed(
        session=session,
        chunks=chunks,
        version_id=version.id,
        doc_id=document.id,
        doc_kind="knowledge_document",
        institution_id=document.institution_id,
        required_roles=roles,
        doc_type=document.doc_type,
        create_chunk=create_chunk,
        clear_existing=clear_existing,
    )
    version.lifecycle_status = KnowledgeDocumentVersionStatus.READY
    version.failure_reason = None
    job.status = IngestJobStatus.SUCCEEDED
    job.error = None
    session.commit()

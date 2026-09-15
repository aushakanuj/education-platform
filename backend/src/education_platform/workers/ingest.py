"""Ingest worker: parse → chunk → embed → index uploaded PDFs."""

from __future__ import annotations

import base64
import io
import logging
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import torch
from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from education_platform.core.config import Settings, get_settings
from education_platform.core.llm import chat_completion_vision_sync
from education_platform.db.session import sync_session
from education_platform.modules.academics.models import (
    AcademicPeriod,
    GradeSubjectOffering,
    PeriodGrade,
    Subtopic,
    Topic,
)
from education_platform.modules.generation.models import ContentGenerationRun
from education_platform.modules.generation.worker import fail_run_for_intake, on_intake_indexed
from education_platform.modules.materials.models import (
    SourceChunk,
    SourceMaterial,
    SourceMaterialVersion,
    SourceMaterialVersionStatus,
)
from education_platform.modules.progress.types import ProgressSubject, run_subject, version_subject
from education_platform.modules.progress.wake import publish_wake
from education_platform.modules.rag import storage
from education_platform.modules.rag.chunking import (
    FORMULA_NOT_DECODED,
    TextChunk,
    _is_blank_or_undecoded_formula,
    _is_formula_item,
    chunk_docling_document,
)
from education_platform.modules.rag.contracts import IngestJobClaim
from education_platform.modules.rag.embeddings import embed_texts
from education_platform.modules.rag.models import (
    IngestJob,
    IngestJobStatus,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    KnowledgeDocumentVersionStatus,
)
from education_platform.modules.rag.vector_store import VectorRow, delete_by_version, upsert_rows

logger = logging.getLogger(__name__)

ParsePdfFn = Callable[[Path], list[TextChunk]]

_CODEFORMULA_MPS_PATCHED = False
FORMULA_VISION_PROMPT = (
    "Return one LaTeX expression only for the mathematical formula in this image. "
    "Do not wrap it in $ or $$ fences. Do not add any prose."
)


def mps_is_available() -> bool:
    """True when PyTorch can run on Apple Silicon Metal (MPS)."""
    return bool(torch.backends.mps.is_built() and torch.backends.mps.is_available())


def docling_accelerator_device() -> str:
    """Docling ``AcceleratorOptions.device``: MPS on Apple Silicon, else CPU."""
    return "mps" if mps_is_available() else "cpu"


def _allow_mps_on_codeformula_transformers() -> None:
    """Let CodeFormula's Transformers engine use Metal.

    ``TransformersVlmEngine`` and legacy ``CodeFormulaModel`` pass
    ``supported_devices=[CPU, CUDA, XPU]`` into ``decide_device``. AUTO then
    strips MPS and falls back to CPU; an explicit MPS request raises. Layout
    already lists MPS; the VLM path is the bottleneck and does run on Metal
    once ``device_map='mps'``.
    """
    global _CODEFORMULA_MPS_PATCHED
    if _CODEFORMULA_MPS_PATCHED:
        return
    from docling.datamodel.accelerator_options import AcceleratorDevice
    from docling.models.inference_engines.vlm import transformers_engine as te
    from docling.models.stages.code_formula import code_formula_model as cfm

    def _with_mps(decide: Callable[..., str]) -> Callable[..., str]:
        def wrapped(
            accelerator_device: str,
            supported_devices: list[Any] | None = None,
        ) -> str:
            if supported_devices is not None and AcceleratorDevice.MPS not in supported_devices:
                supported_devices = [*supported_devices, AcceleratorDevice.MPS]
            return decide(accelerator_device, supported_devices)

        return wrapped

    te.decide_device = _with_mps(te.decide_device)  # type: ignore[attr-defined]
    cfm.decide_device = _with_mps(cfm.decide_device)  # type: ignore[attr-defined]
    _CODEFORMULA_MPS_PATCHED = True
    logger.info("CodeFormula Transformers engine: MPS added to supported_devices")


def apply_formula_pipeline_options(options: Any) -> Any:
    """Keep table structure and page images; never load local CodeFormula.

    ``do_formula_enrichment`` would download and run CodeFormulaV2 (tens of
    minutes on CPU/MPS). Instead we keep rendered page images so
    ``FormulaItem.get_image`` can crop after convert and OpenRouter vision can
    fill LaTeX. TableFormer stays on so policy tables survive as markdown.
    """
    options.do_formula_enrichment = False
    options.generate_page_images = True
    options.do_table_structure = True
    device = docling_accelerator_device()
    accel = getattr(options, "accelerator_options", None)
    if accel is None:
        options.accelerator_options = SimpleNamespace(device=device)
    else:
        accel.device = device
    return options


def _png_base64(image: Any) -> str | None:
    if image is None:
        return None
    try:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
    except Exception:
        logger.exception("Failed to encode formula crop as PNG")
        return None
    return base64.standard_b64encode(buf.getvalue()).decode("ascii")


def _latex_from_vision_response(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("latex"):
            cleaned = cleaned[5:]
        cleaned = cleaned.strip()
    if cleaned.startswith("$$") and cleaned.endswith("$$") and len(cleaned) >= 4:
        cleaned = cleaned[2:-2].strip()
    elif cleaned.startswith("$") and cleaned.endswith("$") and len(cleaned) >= 2:
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _formula_vision_messages(image_png_base64: str) -> list[dict[str, Any]]:
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": FORMULA_VISION_PROMPT},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_png_base64}"},
                },
            ],
        }
    ]


def enrich_formulas_with_openrouter(
    document: Any,
    *,
    settings: Settings | None = None,
) -> None:
    """Fill empty / undecoded FormulaItem.text with OpenRouter vision LaTeX.

    Missing key, failed crops, and API errors leave orig in place. Ingest must
    not fail the PDF.
    """
    cfg = settings or get_settings()
    if not cfg.openrouter_configured:
        return
    iterate = getattr(document, "iterate_items", None)
    if iterate is None:
        return
    enriched = 0
    skipped = 0
    for item, _level in iterate():
        if not _is_formula_item(item):
            continue
        text = str(getattr(item, "text", "") or "")
        if not _is_blank_or_undecoded_formula(text):
            continue
        try:
            crop = item.get_image(document)
            encoded = _png_base64(crop)
            if not encoded:
                skipped += 1
                continue
            latex = _latex_from_vision_response(
                chat_completion_vision_sync(
                    _formula_vision_messages(encoded),
                    settings=cfg,
                )
            )
            if not latex or latex == FORMULA_NOT_DECODED:
                skipped += 1
                continue
            item.text = latex
            enriched += 1
        except Exception:
            logger.exception("OpenRouter formula vision failed; keeping orig")
            skipped += 1
            continue
    logger.info("OpenRouter formula vision: enriched=%s skipped=%s", enriched, skipped)


def convert_pdf_with_docling(path: Path) -> Any:
    """Convert a PDF to a DoclingDocument (lazy import; keeps layout structure)."""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    pipeline_options = apply_formula_pipeline_options(PdfPipelineOptions())
    logger.info(
        "Docling convert accelerator_options.device=%s mps_available=%s "
        "do_formula_enrichment=%s generate_page_images=%s do_table_structure=%s",
        pipeline_options.accelerator_options.device,
        mps_is_available(),
        pipeline_options.do_formula_enrichment,
        pipeline_options.generate_page_images,
        pipeline_options.do_table_structure,
    )
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
    )
    result = converter.convert(str(path))
    document = result.document
    enrich_formulas_with_openrouter(document)
    return document


def parse_pdf_with_docling(path: Path) -> list[TextChunk]:
    """Parse a PDF with Docling and chunk via HybridChunker."""
    document = convert_pdf_with_docling(path)
    return chunk_docling_document(document)


def _sync_session() -> Session:
    return sync_session()


def _wake_ingest(session: Session, job: IngestJob) -> None:
    subjects: list[ProgressSubject] = []
    if job.source_material_version_id is not None:
        subjects.append(version_subject(job.source_material_version_id))
        run_id = session.scalar(
            select(ContentGenerationRun.id).where(
                ContentGenerationRun.intake_source_material_version_id
                == job.source_material_version_id
            )
        )
        if run_id is not None:
            subjects.append(run_subject(run_id))
    if job.knowledge_document_version_id is not None:
        subjects.append(version_subject(job.knowledge_document_version_id))
    if subjects:
        publish_wake(session, *subjects)


def _fail_job(session: Session, job: IngestJob, reason: str) -> None:
    job.status = IngestJobStatus.FAILED
    job.error = reason
    _wake_ingest(session, job)
    session.commit()


def _mark_source_failed(session: Session, version: SourceMaterialVersion, reason: str) -> None:
    version.lifecycle_status = SourceMaterialVersionStatus.FAILED
    version.failure_reason = reason


def _mark_knowledge_failed(
    session: Session, version: KnowledgeDocumentVersion, reason: str
) -> None:
    version.lifecycle_status = KnowledgeDocumentVersionStatus.FAILED
    version.failure_reason = reason


def _fail_source_ingest(
    session: Session, job: IngestJob, version: SourceMaterialVersion, reason: str
) -> None:
    _mark_source_failed(session, version, reason)
    fail_run_for_intake(session, version.id, reason)
    _fail_job(session, job, reason)


def _institution_for_material(session: Session, material: SourceMaterial) -> UUID | None:
    if material.topic_id is not None:
        return session.scalar(
            select(AcademicPeriod.institution_id)
            .select_from(Topic)
            .join(
                GradeSubjectOffering,
                GradeSubjectOffering.id == Topic.grade_subject_offering_id,
            )
            .join(PeriodGrade, PeriodGrade.id == GradeSubjectOffering.period_grade_id)
            .join(AcademicPeriod, AcademicPeriod.id == PeriodGrade.academic_period_id)
            .where(Topic.id == material.topic_id)
        )
    return session.scalar(
        select(AcademicPeriod.institution_id)
        .select_from(Subtopic)
        .join(Topic, Topic.id == Subtopic.topic_id)
        .join(GradeSubjectOffering, GradeSubjectOffering.id == Topic.grade_subject_offering_id)
        .join(PeriodGrade, PeriodGrade.id == GradeSubjectOffering.period_grade_id)
        .join(AcademicPeriod, AcademicPeriod.id == PeriodGrade.academic_period_id)
        .where(Subtopic.id == material.subtopic_id)
    )


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
            if claim.source_material_version_id is not None:
                _process_source_material(session, job, parse)
            elif claim.knowledge_document_version_id is not None:
                _process_knowledge_document(session, job, parse)
            else:
                _fail_job(session, job, "Ingest job has no target set")
        except Exception as exc:
            logger.exception("Ingest job %s failed", ingest_job_id)
            session.rollback()
            job = session.get(IngestJob, UUID(ingest_job_id))
            if job is None:
                return
            reason = str(exc)[:2000]
            if job.source_material_version_id is not None:
                version = session.get(SourceMaterialVersion, job.source_material_version_id)
                if version is not None:
                    _mark_source_failed(session, version, reason)
                    fail_run_for_intake(session, version.id, reason)
            elif job.knowledge_document_version_id is not None:
                version_k = session.get(KnowledgeDocumentVersion, job.knowledge_document_version_id)
                if version_k is not None:
                    _mark_knowledge_failed(session, version_k, reason)
            job.status = IngestJobStatus.FAILED
            job.error = reason
            _wake_ingest(session, job)
            session.commit()
    finally:
        session.close()


def _process_source_material(session: Session, job: IngestJob, parse: ParsePdfFn) -> None:
    version = session.get(SourceMaterialVersion, job.source_material_version_id)
    if version is None:
        _fail_job(session, job, "Source material version not found")
        return

    version.lifecycle_status = SourceMaterialVersionStatus.PROCESSING
    version.failure_reason = None
    _wake_ingest(session, job)
    session.commit()

    if not version.blob_object_key:
        _fail_source_ingest(session, job, version, "Missing blob object key")
        return

    path = storage.resolve_blob_path(version.blob_object_key)
    chunks = parse(path)
    if not chunks:
        _fail_source_ingest(session, job, version, "No extractable text")
        return

    material = session.get(SourceMaterial, version.source_material_id)
    if material is None:
        _fail_source_ingest(session, job, version, "Source material missing")
        return

    institution_id = _institution_for_material(session, material)
    if institution_id is None:
        _fail_source_ingest(session, job, version, "Unable to resolve institution")
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

    required_roles = (
        ["teacher", "administrator"]
        if material.topic_id is not None
        else ["student", "teacher", "administrator"]
    )
    _persist_and_embed(
        session=session,
        chunks=chunks,
        version_id=version.id,
        doc_id=material.id,
        doc_kind="source_material_version",
        institution_id=institution_id,
        required_roles=required_roles,
        doc_type="curriculum",
        create_chunk=create_chunk,
        clear_existing=clear_existing,
    )
    version.lifecycle_status = SourceMaterialVersionStatus.READY
    version.failure_reason = None
    on_intake_indexed(session, version.id)
    job.status = IngestJobStatus.SUCCEEDED
    job.error = None
    _wake_ingest(session, job)
    session.commit()


def _process_knowledge_document(session: Session, job: IngestJob, parse: ParsePdfFn) -> None:
    version = session.get(KnowledgeDocumentVersion, job.knowledge_document_version_id)
    if version is None:
        _fail_job(session, job, "Knowledge document version not found")
        return

    version.lifecycle_status = KnowledgeDocumentVersionStatus.PROCESSING
    version.failure_reason = None
    _wake_ingest(session, job)
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
        doc_kind="knowledge_document_version",
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
    _wake_ingest(session, job)
    session.commit()

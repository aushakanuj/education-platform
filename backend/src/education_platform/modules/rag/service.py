"""Admin knowledge-document uploads; queue is Postgres ``ingest_jobs``."""

from __future__ import annotations

import re
from typing import cast
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.api.deps import Principal
from education_platform.core.config import get_settings
from education_platform.modules.academics.models import (
    AcademicPeriod,
    GradeSubjectOffering,
    PeriodGrade,
    Subtopic,
    Topic,
)
from education_platform.modules.auth.models import Institution
from education_platform.modules.materials.models import (
    SourceChunk,
    SourceMaterial,
    SourceMaterialStatus,
    SourceMaterialVersion,
    SourceMaterialVersionStatus,
)
from education_platform.modules.rag import storage
from education_platform.modules.rag.contracts import parse_required_roles
from education_platform.modules.rag.models import (
    IngestJob,
    IngestJobStatus,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeDocumentVersion,
    KnowledgeDocumentVersionStatus,
)
from education_platform.modules.rag.schemas import (
    KnowledgeDocumentDetailOut,
    KnowledgeDocumentOut,
    KnowledgeDocumentVersionSummary,
    KnowledgeIngestAccepted,
    KnowledgeVersionStatusOut,
    MaterialIngestAccepted,
    MaterialVersionStatusOut,
)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str, *, fallback: str = "document") -> str:
    slug = _SLUG_RE.sub("-", value.strip().lower()).strip("-")
    return (slug[:100] or fallback)[:100]


def _validated_required_roles(raw: str | None) -> list[str]:
    try:
        return parse_required_roles(raw)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid required_roles: {exc.errors()[0]['msg']}",
        ) from exc


def _validate_upload(file: UploadFile, data: bytes) -> str:
    settings = get_settings()
    content_type = (file.content_type or "").split(";")[0].strip().lower() or "application/pdf"
    if content_type not in settings.ingest_allowed_content_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported content type: {content_type}",
        )
    if len(data) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty upload")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds max size of {settings.max_upload_bytes} bytes",
        )
    return content_type


async def _subtopic_in_institution(
    session: AsyncSession, *, subtopic_id: UUID, institution_id: UUID
) -> Subtopic | None:
    return cast(
        Subtopic | None,
        await session.scalar(
            select(Subtopic)
            .join(Topic, Topic.id == Subtopic.topic_id)
            .join(GradeSubjectOffering, GradeSubjectOffering.id == Topic.grade_subject_offering_id)
            .join(PeriodGrade, PeriodGrade.id == GradeSubjectOffering.period_grade_id)
            .join(AcademicPeriod, AcademicPeriod.id == PeriodGrade.academic_period_id)
            .join(Institution, Institution.id == AcademicPeriod.institution_id)
            .where(Subtopic.id == subtopic_id, Institution.id == institution_id)
        ),
    )


async def upload_curriculum_material(
    session: AsyncSession,
    principal: Principal,
    *,
    subtopic_id: UUID,
    title: str,
    file: UploadFile,
) -> MaterialIngestAccepted:
    subtopic = await _subtopic_in_institution(
        session, subtopic_id=subtopic_id, institution_id=principal.institution_id
    )
    if subtopic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subtopic not found")

    data = await file.read()
    content_type = _validate_upload(file, data)
    checksum = storage.sha256_hex(data)
    object_key = storage.build_object_key(
        institution_id=principal.institution_id,
        kind="source_materials",
        filename=file.filename or "material.pdf",
    )
    storage.store_bytes(object_key, data)

    material = await session.scalar(
        select(SourceMaterial).where(
            SourceMaterial.subtopic_id == subtopic_id,
            SourceMaterial.slug == "lesson",
        )
    )
    if material is None:
        material = SourceMaterial(
            subtopic_id=subtopic_id,
            title=title.strip() or "Lesson",
            slug="lesson",
            status=SourceMaterialStatus.DRAFT,
        )
        session.add(material)
        await session.flush()

    next_version = await session.scalar(
        select(func.coalesce(func.max(SourceMaterialVersion.version_number), 0)).where(
            SourceMaterialVersion.source_material_id == material.id
        )
    )
    version_number = int(next_version or 0) + 1
    version = SourceMaterialVersion(
        source_material_id=material.id,
        version_number=version_number,
        lifecycle_status=SourceMaterialVersionStatus.PROCESSING,
        title=title.strip() or material.title,
        content_format="pdf",
        blob_object_key=object_key,
        blob_content_type=content_type,
        checksum=checksum,
    )
    session.add(version)
    await session.flush()

    job = IngestJob(
        id=uuid4(),
        source_material_version_id=version.id,
        status=IngestJobStatus.QUEUED,
    )
    session.add(job)
    await session.commit()
    await session.refresh(version)
    await session.refresh(job)

    return MaterialIngestAccepted(
        source_material_id=material.id,
        version_id=version.id,
        version_number=version.version_number,
        lifecycle_status=version.lifecycle_status.value,
        title=version.title,
        ingest_job_id=job.id,
    )


async def get_material_version_status(
    session: AsyncSession,
    principal: Principal,
    version_id: UUID,
) -> MaterialVersionStatusOut:
    row = await session.execute(
        select(SourceMaterialVersion, SourceMaterial)
        .join(SourceMaterial, SourceMaterial.id == SourceMaterialVersion.source_material_id)
        .where(SourceMaterialVersion.id == version_id)
    )
    result = row.first()
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    version, material = result
    subtopic = await _subtopic_in_institution(
        session, subtopic_id=material.subtopic_id, institution_id=principal.institution_id
    )
    if subtopic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")

    chunk_count = int(
        await session.scalar(
            select(func.count())
            .select_from(SourceChunk)
            .where(SourceChunk.source_material_version_id == version.id)
        )
        or 0
    )
    return MaterialVersionStatusOut(
        id=version.id,
        source_material_id=version.source_material_id,
        version_number=version.version_number,
        title=version.title,
        lifecycle_status=version.lifecycle_status.value,
        failure_reason=version.failure_reason,
        chunk_count=chunk_count,
        blob_content_type=version.blob_content_type,
    )


async def upload_knowledge_document(
    session: AsyncSession,
    principal: Principal,
    *,
    title: str,
    doc_type: str,
    required_roles_raw: str | None,
    file: UploadFile,
) -> KnowledgeIngestAccepted:
    data = await file.read()
    content_type = _validate_upload(file, data)
    checksum = storage.sha256_hex(data)
    object_key = storage.build_object_key(
        institution_id=principal.institution_id,
        kind="knowledge_documents",
        filename=file.filename or "document.pdf",
    )
    storage.store_bytes(object_key, data)

    base_slug = slugify(title)
    slug = base_slug
    suffix = 2
    while await session.scalar(
        select(KnowledgeDocument.id).where(
            KnowledgeDocument.institution_id == principal.institution_id,
            KnowledgeDocument.slug == slug,
        )
    ):
        slug = f"{base_slug[:90]}-{suffix}"
        suffix += 1

    document = KnowledgeDocument(
        institution_id=principal.institution_id,
        title=title.strip(),
        slug=slug,
        doc_type=doc_type.strip() or "policy",
        status=KnowledgeDocumentStatus.DRAFT,
        required_roles=_validated_required_roles(required_roles_raw),
    )
    session.add(document)
    await session.flush()

    version = KnowledgeDocumentVersion(
        document_id=document.id,
        version_number=1,
        lifecycle_status=KnowledgeDocumentVersionStatus.PROCESSING,
        blob_object_key=object_key,
        blob_content_type=content_type,
        checksum=checksum,
    )
    session.add(version)
    await session.flush()

    job = IngestJob(
        id=uuid4(),
        knowledge_document_version_id=version.id,
        status=IngestJobStatus.QUEUED,
    )
    session.add(job)
    await session.commit()
    await session.refresh(document)
    await session.refresh(version)
    await session.refresh(job)

    return KnowledgeIngestAccepted(
        document_id=document.id,
        version_id=version.id,
        version_number=version.version_number,
        lifecycle_status=version.lifecycle_status.value,
        title=document.title,
        doc_type=document.doc_type,
        ingest_job_id=job.id,
    )


async def list_knowledge_documents(
    session: AsyncSession, principal: Principal
) -> list[KnowledgeDocumentOut]:
    docs = (
        await session.scalars(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.institution_id == principal.institution_id)
            .order_by(KnowledgeDocument.created_at.desc())
        )
    ).all()
    out: list[KnowledgeDocumentOut] = []
    for doc in docs:
        latest = await session.scalar(
            select(KnowledgeDocumentVersion)
            .where(KnowledgeDocumentVersion.document_id == doc.id)
            .order_by(KnowledgeDocumentVersion.version_number.desc())
            .limit(1)
        )
        latest_summary = None
        if latest is not None:
            chunk_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(KnowledgeChunk)
                    .where(KnowledgeChunk.knowledge_document_version_id == latest.id)
                )
                or 0
            )
            latest_summary = KnowledgeDocumentVersionSummary(
                id=latest.id,
                version_number=latest.version_number,
                lifecycle_status=latest.lifecycle_status.value,
                failure_reason=latest.failure_reason,
                chunk_count=chunk_count,
                created_at=latest.created_at,
            )
        roles = [str(r) for r in (doc.required_roles or [])]
        out.append(
            KnowledgeDocumentOut(
                id=doc.id,
                title=doc.title,
                slug=doc.slug,
                doc_type=doc.doc_type,
                status=doc.status.value,
                required_roles=roles,
                latest_version=latest_summary,
            )
        )
    return out


async def get_knowledge_document(
    session: AsyncSession, principal: Principal, document_id: UUID
) -> KnowledgeDocumentDetailOut:
    document = await session.get(KnowledgeDocument, document_id)
    if document is None or document.institution_id != principal.institution_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    versions = (
        await session.scalars(
            select(KnowledgeDocumentVersion)
            .where(KnowledgeDocumentVersion.document_id == document.id)
            .order_by(KnowledgeDocumentVersion.version_number.desc())
        )
    ).all()
    summaries: list[KnowledgeDocumentVersionSummary] = []
    for version in versions:
        chunk_count = int(
            await session.scalar(
                select(func.count())
                .select_from(KnowledgeChunk)
                .where(KnowledgeChunk.knowledge_document_version_id == version.id)
            )
            or 0
        )
        summaries.append(
            KnowledgeDocumentVersionSummary(
                id=version.id,
                version_number=version.version_number,
                lifecycle_status=version.lifecycle_status.value,
                failure_reason=version.failure_reason,
                chunk_count=chunk_count,
                created_at=version.created_at,
            )
        )
    return KnowledgeDocumentDetailOut(
        id=document.id,
        title=document.title,
        slug=document.slug,
        doc_type=document.doc_type,
        status=document.status.value,
        required_roles=[str(r) for r in (document.required_roles or [])],
        versions=summaries,
    )


async def get_knowledge_version_status(
    session: AsyncSession, principal: Principal, version_id: UUID
) -> KnowledgeVersionStatusOut:
    row = await session.execute(
        select(KnowledgeDocumentVersion, KnowledgeDocument)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeDocumentVersion.document_id)
        .where(KnowledgeDocumentVersion.id == version_id)
    )
    result = row.first()
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    version, document = result
    if document.institution_id != principal.institution_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")

    chunk_count = int(
        await session.scalar(
            select(func.count())
            .select_from(KnowledgeChunk)
            .where(KnowledgeChunk.knowledge_document_version_id == version.id)
        )
        or 0
    )
    return KnowledgeVersionStatusOut(
        id=version.id,
        document_id=version.document_id,
        version_number=version.version_number,
        lifecycle_status=version.lifecycle_status.value,
        failure_reason=version.failure_reason,
        chunk_count=chunk_count,
        blob_content_type=version.blob_content_type,
    )

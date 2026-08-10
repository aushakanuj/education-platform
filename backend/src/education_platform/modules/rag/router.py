"""Admin knowledge-document ingest routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.api.deps import Principal, require_administrator
from education_platform.db.session import get_session
from education_platform.modules.rag import service
from education_platform.modules.rag.schemas import (
    KnowledgeDocumentDetailOut,
    KnowledgeDocumentOut,
    KnowledgeIngestAccepted,
    KnowledgeVersionStatusOut,
)

router = APIRouter(tags=["rag-admin"])


@router.post(
    "/admin/knowledge-documents",
    response_model=KnowledgeIngestAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_knowledge_document(
    title: str = Form(...),
    doc_type: str = Form(...),
    required_roles: str | None = Form(default=None),
    file: UploadFile = File(...),
    principal: Principal = Depends(require_administrator),
    session: AsyncSession = Depends(get_session),
) -> KnowledgeIngestAccepted:
    return await service.upload_knowledge_document(
        session,
        principal,
        title=title,
        doc_type=doc_type,
        required_roles_raw=required_roles,
        file=file,
    )


@router.get("/admin/knowledge-documents", response_model=list[KnowledgeDocumentOut])
async def list_knowledge_documents(
    principal: Principal = Depends(require_administrator),
    session: AsyncSession = Depends(get_session),
) -> list[KnowledgeDocumentOut]:
    return await service.list_knowledge_documents(session, principal)


@router.get("/admin/knowledge-documents/{document_id}", response_model=KnowledgeDocumentDetailOut)
async def get_knowledge_document(
    document_id: UUID,
    principal: Principal = Depends(require_administrator),
    session: AsyncSession = Depends(get_session),
) -> KnowledgeDocumentDetailOut:
    return await service.get_knowledge_document(session, principal, document_id)


@router.get(
    "/admin/knowledge-document-versions/{version_id}",
    response_model=KnowledgeVersionStatusOut,
)
async def get_knowledge_document_version(
    version_id: UUID,
    principal: Principal = Depends(require_administrator),
    session: AsyncSession = Depends(get_session),
) -> KnowledgeVersionStatusOut:
    return await service.get_knowledge_version_status(session, principal, version_id)

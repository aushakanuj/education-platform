"""Knowledge documents, chunks, and ingest job observability models."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from education_platform.db.base import Base, UUIDTimestampMixin
from education_platform.db.types import JsonDict, partial_unique_index, str_enum


class KnowledgeDocumentStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class KnowledgeDocumentVersionStatus(str, enum.Enum):
    DRAFT = "draft"
    PROCESSING = "processing"
    READY = "ready"
    PUBLISHED = "published"
    FAILED = "failed"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class IngestTargetKind(str, enum.Enum):
    SOURCE_MATERIAL_VERSION = "source_material_version"
    KNOWLEDGE_DOCUMENT_VERSION = "knowledge_document_version"


class IngestJobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class KnowledgeDocument(UUIDTimestampMixin, Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        UniqueConstraint(
            "institution_id",
            "slug",
            name="uq_knowledge_documents_institution_slug",
        ),
    )

    institution_id: Mapped[UUID] = mapped_column(ForeignKey("institutions.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(100))
    doc_type: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[KnowledgeDocumentStatus] = mapped_column(
        str_enum(KnowledgeDocumentStatus, "knowledge_document_status"),
        default=KnowledgeDocumentStatus.DRAFT,
        index=True,
    )
    required_roles: Mapped[list[Any]] = mapped_column(
        JsonDict,
        default=lambda: ["administrator", "teacher"],
    )


class KnowledgeDocumentVersion(UUIDTimestampMixin, Base):
    __tablename__ = "knowledge_document_versions"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_knowledge_document_versions_document_version",
        ),
        partial_unique_index(
            "uq_knowledge_document_versions_one_published",
            "document_id",
            where="lifecycle_status = 'published'",
        ),
        CheckConstraint(
            "version_number >= 1",
            name="ck_knowledge_document_versions_version_number",
        ),
    )

    document_id: Mapped[UUID] = mapped_column(ForeignKey("knowledge_documents.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    lifecycle_status: Mapped[KnowledgeDocumentVersionStatus] = mapped_column(
        str_enum(KnowledgeDocumentVersionStatus, "knowledge_document_version_status"),
        default=KnowledgeDocumentVersionStatus.DRAFT,
        index=True,
    )
    blob_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    blob_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgeChunk(UUIDTimestampMixin, Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint(
            "knowledge_document_version_id",
            "content_hash",
            name="uq_knowledge_chunks_version_content_hash",
        ),
        CheckConstraint("ordinal >= 1", name="ck_knowledge_chunks_ordinal"),
        CheckConstraint(
            "token_count IS NULL OR token_count >= 0",
            name="ck_knowledge_chunks_token_count",
        ),
    )

    knowledge_document_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_document_versions.id"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_heading: Mapped[str | None] = mapped_column(String(500), nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)


class IngestJob(UUIDTimestampMixin, Base):
    __tablename__ = "ingest_jobs"
    __table_args__ = (
        CheckConstraint(
            "target_kind IN ('source_material_version', 'knowledge_document_version')",
            name="ck_ingest_jobs_target_kind",
        ),
        Index("ix_ingest_jobs_status_created_at", "status", "created_at"),
    )

    target_kind: Mapped[IngestTargetKind] = mapped_column(
        str_enum(IngestTargetKind, "ingest_target_kind"),
        index=True,
    )
    target_id: Mapped[UUID] = mapped_column(index=True)
    status: Mapped[IngestJobStatus] = mapped_column(
        str_enum(IngestJobStatus, "ingest_job_status"),
        default=IngestJobStatus.QUEUED,
        index=True,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ChunkEmbedding(Base):
    """pgvector row for a source/knowledge chunk embedding."""

    __tablename__ = "chunk_embeddings"

    chunk_id: Mapped[UUID] = mapped_column(primary_key=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(384))
    doc_id: Mapped[UUID] = mapped_column()
    doc_kind: Mapped[str] = mapped_column(String(50))
    institution_id: Mapped[UUID] = mapped_column(index=True)
    required_roles: Mapped[list[Any]] = mapped_column(JsonDict)
    doc_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version_id: Mapped[UUID] = mapped_column(index=True)

"""Source material persistence models and student progress."""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from education_platform.db.base import Base, UUIDTimestampMixin
from education_platform.db.types import partial_unique_index, str_enum


class SourceMaterialStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class SourceMaterialVersionStatus(str, enum.Enum):
    DRAFT = "draft"
    PROCESSING = "processing"
    READY = "ready"
    PUBLISHED = "published"
    FAILED = "failed"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class MaterialProgressStatus(str, enum.Enum):
    OPENED = "opened"
    COMPLETED = "completed"


class SourceMaterial(UUIDTimestampMixin, Base):
    __tablename__ = "source_materials"
    __table_args__ = (
        UniqueConstraint("subtopic_id", "slug", name="uq_source_materials_subtopic_slug"),
    )

    subtopic_id: Mapped[UUID] = mapped_column(ForeignKey("subtopics.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(100))
    status: Mapped[SourceMaterialStatus] = mapped_column(
        str_enum(SourceMaterialStatus, "source_material_status"),
        default=SourceMaterialStatus.DRAFT,
        index=True,
    )


class SourceMaterialVersion(UUIDTimestampMixin, Base):
    __tablename__ = "source_material_versions"
    __table_args__ = (
        UniqueConstraint(
            "source_material_id",
            "version_number",
            name="uq_source_material_versions_material_version",
        ),
        partial_unique_index(
            "uq_source_material_versions_one_published",
            "source_material_id",
            where="lifecycle_status = 'published'",
        ),
        CheckConstraint("version_number >= 1", name="ck_source_material_versions_version_number"),
    )

    source_material_id: Mapped[UUID] = mapped_column(ForeignKey("source_materials.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    lifecycle_status: Mapped[SourceMaterialVersionStatus] = mapped_column(
        str_enum(SourceMaterialVersionStatus, "source_material_version_status"),
        default=SourceMaterialVersionStatus.DRAFT,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200))
    content_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_format: Mapped[str] = mapped_column(String(50), default="markdown")
    blob_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    blob_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SourceChunk(UUIDTimestampMixin, Base):
    """Normalized text chunk produced by curriculum material ingestion."""

    __tablename__ = "source_chunks"
    __table_args__ = (
        UniqueConstraint(
            "source_material_version_id",
            "content_hash",
            name="uq_source_chunks_version_content_hash",
        ),
        CheckConstraint("ordinal >= 1", name="ck_source_chunks_ordinal"),
        CheckConstraint(
            "token_count IS NULL OR token_count >= 0",
            name="ck_source_chunks_token_count",
        ),
    )

    source_material_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_material_versions.id"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_heading: Mapped[str | None] = mapped_column(String(500), nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)


class StudentMaterialProgress(UUIDTimestampMixin, Base):
    """Student progress against an immutable published material version."""

    __tablename__ = "student_material_progress"
    __table_args__ = (
        UniqueConstraint(
            "student_subject_enrollment_id",
            "source_material_version_id",
            name="uq_student_material_progress_enrollment_version",
        ),
        CheckConstraint(
            "(status = 'opened' AND completed_at IS NULL) OR "
            "(status = 'completed' AND completed_at IS NOT NULL)",
            name="ck_student_material_progress_status_timestamps",
        ),
        CheckConstraint(
            "last_unit_ordinal IS NULL OR last_unit_ordinal >= 1",
            name="ck_student_material_progress_last_unit",
        ),
    )

    student_subject_enrollment_id: Mapped[UUID] = mapped_column(
        ForeignKey("student_subject_enrollments.id"), index=True
    )
    source_material_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_material_versions.id"), index=True
    )
    status: Mapped[MaterialProgressStatus] = mapped_column(
        str_enum(MaterialProgressStatus, "material_progress_status"),
        default=MaterialProgressStatus.OPENED,
        index=True,
    )
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_unit_ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True)

import enum
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from education_platform.db.base import Base, UUIDTimestampMixin


class DocumentStatus(str, enum.Enum):
    DRAFT = "draft"
    PROCESSING = "processing"
    READY = "ready"
    PUBLISHED = "published"
    FAILED = "failed"
    ARCHIVED = "archived"


class CurriculumCollection(UUIDTimestampMixin, Base):
    __tablename__ = "curriculum_collections"

    institution_id: Mapped[UUID] = mapped_column(ForeignKey("institutions.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class TeacherCollectionAssignment(UUIDTimestampMixin, Base):
    __tablename__ = "teacher_collection_assignments"
    __table_args__ = (UniqueConstraint("teacher_id", "collection_id"),)

    teacher_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    collection_id: Mapped[UUID] = mapped_column(ForeignKey("curriculum_collections.id"), index=True)


class CurriculumDocument(UUIDTimestampMixin, Base):
    __tablename__ = "curriculum_documents"

    collection_id: Mapped[UUID] = mapped_column(ForeignKey("curriculum_collections.id"), index=True)
    uploaded_by_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    object_key: Mapped[str] = mapped_column(String(500), unique=True)
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus), default=DocumentStatus.DRAFT
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class DocumentChunk(UUIDTimestampMixin, Base):
    __tablename__ = "document_chunks"

    document_id: Mapped[UUID] = mapped_column(ForeignKey("curriculum_documents.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    source_locator: Mapped[str | None] = mapped_column(String(200), nullable=True)

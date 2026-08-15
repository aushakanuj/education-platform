"""RAG ingest foundation: source chunks, knowledge docs, ingest jobs.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-10 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_chunks",
        sa.Column("source_material_version_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("section_heading", sa.String(length=500), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint("ordinal >= 1", name="ck_source_chunks_ordinal"),
        sa.CheckConstraint(
            "token_count IS NULL OR token_count >= 0",
            name="ck_source_chunks_token_count",
        ),
        sa.ForeignKeyConstraint(
            ["source_material_version_id"],
            ["source_material_versions.id"],
            name=op.f("fk_source_chunks_source_material_version_id_source_material_versions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_chunks")),
        sa.UniqueConstraint(
            "source_material_version_id",
            "content_hash",
            name="uq_source_chunks_version_content_hash",
        ),
    )
    op.create_index(
        op.f("ix_source_chunks_source_material_version_id"),
        "source_chunks",
        ["source_material_version_id"],
        unique=False,
    )

    op.create_table(
        "knowledge_documents",
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("doc_type", sa.String(length=50), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "active",
                "archived",
                name="knowledge_document_status",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("required_roles", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name=op.f("fk_knowledge_documents_institution_id_institutions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_documents")),
        sa.UniqueConstraint(
            "institution_id",
            "slug",
            name="uq_knowledge_documents_institution_slug",
        ),
    )
    op.create_index(
        op.f("ix_knowledge_documents_institution_id"),
        "knowledge_documents",
        ["institution_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_documents_doc_type"),
        "knowledge_documents",
        ["doc_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_documents_status"),
        "knowledge_documents",
        ["status"],
        unique=False,
    )

    op.create_table(
        "knowledge_document_versions",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "lifecycle_status",
            sa.Enum(
                "draft",
                "processing",
                "ready",
                "published",
                "failed",
                "superseded",
                "archived",
                name="knowledge_document_version_status",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("blob_object_key", sa.String(length=500), nullable=True),
        sa.Column("blob_content_type", sa.String(length=100), nullable=True),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "version_number >= 1",
            name="ck_knowledge_document_versions_version_number",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name=op.f("fk_knowledge_document_versions_document_id_knowledge_documents"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_document_versions")),
        sa.UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_knowledge_document_versions_document_version",
        ),
    )
    op.create_index(
        op.f("ix_knowledge_document_versions_document_id"),
        "knowledge_document_versions",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_document_versions_lifecycle_status"),
        "knowledge_document_versions",
        ["lifecycle_status"],
        unique=False,
    )
    op.create_index(
        "uq_knowledge_document_versions_one_published",
        "knowledge_document_versions",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("lifecycle_status = 'published'"),
    )

    op.create_table(
        "knowledge_chunks",
        sa.Column("knowledge_document_version_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("section_heading", sa.String(length=500), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint("ordinal >= 1", name="ck_knowledge_chunks_ordinal"),
        sa.CheckConstraint(
            "token_count IS NULL OR token_count >= 0",
            name="ck_knowledge_chunks_token_count",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_document_version_id"],
            ["knowledge_document_versions.id"],
            name=op.f(
                "fk_knowledge_chunks_knowledge_document_version_id_knowledge_document_versions"
            ),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_chunks")),
        sa.UniqueConstraint(
            "knowledge_document_version_id",
            "content_hash",
            name="uq_knowledge_chunks_version_content_hash",
        ),
    )
    op.create_index(
        op.f("ix_knowledge_chunks_knowledge_document_version_id"),
        "knowledge_chunks",
        ["knowledge_document_version_id"],
        unique=False,
    )

    op.create_table(
        "ingest_jobs",
        sa.Column(
            "target_kind",
            sa.Enum(
                "source_material_version",
                "knowledge_document_version",
                name="ingest_target_kind",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("redis_job_id", sa.String(length=100), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "running",
                "succeeded",
                "failed",
                name="ingest_job_status",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "target_kind IN ('source_material_version', 'knowledge_document_version')",
            name="ck_ingest_jobs_target_kind",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingest_jobs")),
    )
    op.create_index(
        op.f("ix_ingest_jobs_target_kind"), "ingest_jobs", ["target_kind"], unique=False
    )
    op.create_index(op.f("ix_ingest_jobs_target_id"), "ingest_jobs", ["target_id"], unique=False)
    op.create_index(op.f("ix_ingest_jobs_status"), "ingest_jobs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_ingest_jobs_status"), table_name="ingest_jobs")
    op.drop_index(op.f("ix_ingest_jobs_target_id"), table_name="ingest_jobs")
    op.drop_index(op.f("ix_ingest_jobs_target_kind"), table_name="ingest_jobs")
    op.drop_table("ingest_jobs")

    op.drop_index(
        op.f("ix_knowledge_chunks_knowledge_document_version_id"),
        table_name="knowledge_chunks",
    )
    op.drop_table("knowledge_chunks")

    op.drop_index(
        "uq_knowledge_document_versions_one_published",
        table_name="knowledge_document_versions",
    )
    op.drop_index(
        op.f("ix_knowledge_document_versions_lifecycle_status"),
        table_name="knowledge_document_versions",
    )
    op.drop_index(
        op.f("ix_knowledge_document_versions_document_id"),
        table_name="knowledge_document_versions",
    )
    op.drop_table("knowledge_document_versions")

    op.drop_index(op.f("ix_knowledge_documents_status"), table_name="knowledge_documents")
    op.drop_index(op.f("ix_knowledge_documents_doc_type"), table_name="knowledge_documents")
    op.drop_index(op.f("ix_knowledge_documents_institution_id"), table_name="knowledge_documents")
    op.drop_table("knowledge_documents")

    op.drop_index(op.f("ix_source_chunks_source_material_version_id"), table_name="source_chunks")
    op.drop_table("source_chunks")

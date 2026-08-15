"""Enable pgvector and create chunk_embeddings table.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-15 11:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    op.create_table(
        "chunk_embeddings",
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column("doc_id", sa.Uuid(), nullable=False),
        sa.Column("doc_kind", sa.String(length=50), nullable=False),
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("required_roles", sa.JSON(), nullable=False),
        sa.Column("doc_type", sa.String(length=50), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("chunk_id", name=op.f("pk_chunk_embeddings")),
    )
    op.create_index(
        "ix_chunk_embeddings_version_id",
        "chunk_embeddings",
        ["version_id"],
        unique=False,
    )
    op.create_index(
        "ix_chunk_embeddings_institution_id",
        "chunk_embeddings",
        ["institution_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_chunk_embeddings_institution_id", table_name="chunk_embeddings")
    op.drop_index("ix_chunk_embeddings_version_id", table_name="chunk_embeddings")
    op.drop_table("chunk_embeddings")
    op.execute(sa.text("DROP EXTENSION IF EXISTS vector"))

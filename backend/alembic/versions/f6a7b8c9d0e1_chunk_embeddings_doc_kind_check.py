"""Add CHECK constraint on chunk_embeddings.doc_kind.

`doc_kind` was previously validated only at the Pydantic layer (`Literal["source_material",
"knowledge_document"]`), so any raw insert bypassing that layer could write a garbage value
that the schema catalog's "enum reference" wouldn't actually guarantee. This makes the
allowed values a real database constraint.

Revision ID: f6a7b8c9d0e1
Revises: d3e4f5a6b7c8
Create Date: 2026-08-16 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str | Sequence[str] | None = "f6a7b8c9d0e1"
down_revision: str | Sequence[str] | None = "d3e4f5a6b7c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `op.create_check_constraint` builds its constraint against `target_metadata`
    # (see alembic/env.py), so the project's "ck_%(table_name)s_%(constraint_name)s"
    # naming convention re-templates whatever name is passed here — pass only the
    # unprefixed component ("doc_kind"), not the full name, or it double-prefixes.
    op.create_check_constraint(
        "doc_kind",
        "chunk_embeddings",
        "doc_kind IN ('source_material', 'knowledge_document')",
    )


def downgrade() -> None:
    # Same double-prefixing hazard as above applies to op.drop_constraint when a
    # `type_` is given — pass the unprefixed component here too.
    op.drop_constraint("doc_kind", "chunk_embeddings", type_="check")

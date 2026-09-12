"""Unify chunk_embeddings.doc_kind vocabulary with ingest_jobs.target_kind.

`chunk_embeddings.doc_kind` used the unsuffixed forms `source_material` /
`knowledge_document`, while `ingest_jobs.target_kind` already used the version-grain
forms `source_material_version` / `knowledge_document_version` for the same underlying
split. The two were easy to conflate (a filter literal copied from one column silently
matched zero rows on the other). This migration keeps the more precise, suffixed form —
it names the grain `doc_kind` actually points at (a *version*'s chunks), matching
`target_kind` — and rewrites existing data plus the CHECK constraint to match.

This is a data migration, not just a schema change: existing `chunk_embeddings` rows
must be rewritten in place, or every embedding written before this migration becomes
unfindable by any query that filters on the new vocabulary.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-16 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str | Sequence[str] | None = "a7b8c9d0e1f2"
down_revision: str | Sequence[str] | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_TO_NEW = {
    "source_material": "source_material_version",
    "knowledge_document": "knowledge_document_version",
}


def upgrade() -> None:
    # Drop the old CHECK before rewriting data, so in-flight values never violate it
    # mid-migration. `op.drop_constraint`/`op.create_check_constraint` re-template
    # whatever name they're given against this project's naming convention
    # ("ck_%(table_name)s_%(constraint_name)s") — pass the unprefixed component
    # ("doc_kind"), not the full constraint name, or it double-prefixes.
    op.drop_constraint("doc_kind", "chunk_embeddings", type_="check")

    for old_value, new_value in _OLD_TO_NEW.items():
        op.execute(
            f"UPDATE chunk_embeddings SET doc_kind = '{new_value}' WHERE doc_kind = '{old_value}'"
        )

    op.create_check_constraint(
        "doc_kind",
        "chunk_embeddings",
        "doc_kind IN ('source_material_version', 'knowledge_document_version')",
    )


def downgrade() -> None:
    op.drop_constraint("doc_kind", "chunk_embeddings", type_="check")

    for old_value, new_value in _OLD_TO_NEW.items():
        op.execute(
            f"UPDATE chunk_embeddings SET doc_kind = '{old_value}' WHERE doc_kind = '{new_value}'"
        )

    op.create_check_constraint(
        "doc_kind",
        "chunk_embeddings",
        "doc_kind IN ('source_material', 'knowledge_document')",
    )

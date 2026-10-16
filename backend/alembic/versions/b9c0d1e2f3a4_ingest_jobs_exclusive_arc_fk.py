"""Replace ingest_jobs' polymorphic (target_kind, target_id) with real FKs.

`ingest_jobs.target_id` was a bare UUID with no DB-level FK; `target_kind` told
application code which table to resolve it against. Postgres could never enforce that
the pointed-at row actually existed, and a plain join could never follow it. This
replaces the pair with an "exclusive arc": two nullable, individually FK-constrained
columns (`source_material_version_id`, `knowledge_document_version_id`) plus a CHECK
requiring exactly one to be set. The non-null column alone now tells you the job's
kind, so `target_kind` is redundant and dropped along with `target_id` — neither was
ever surfaced to the frontend/API as a display label (verified: admin ingest-status
endpoints resolve status from `source_material_versions`/`knowledge_document_versions`
directly, never from `ingest_jobs`).

This is a data migration, not just a schema change: existing rows must be backfilled
from `target_kind`/`target_id` into the new columns before the old columns are dropped,
or every in-flight ingest job becomes unresolvable.

Revision ID: b9c0d1e2f3a4
Revises: a7b8c9d0e1f2
Create Date: 2026-08-16 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str | Sequence[str] | None = "b9c0d1e2f3a4"
down_revision: str | Sequence[str] | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ingest_jobs", sa.Column("source_material_version_id", sa.Uuid(), nullable=True))
    op.add_column(
        "ingest_jobs", sa.Column("knowledge_document_version_id", sa.Uuid(), nullable=True)
    )

    op.execute(
        "UPDATE ingest_jobs SET source_material_version_id = target_id "
        "WHERE target_kind = 'source_material_version'"
    )
    op.execute(
        "UPDATE ingest_jobs SET knowledge_document_version_id = target_id "
        "WHERE target_kind = 'knowledge_document_version'"
    )

    # op.f() marks these names as already-final so Alembic's naming convention
    # ("ck_%(table_name)s_%(constraint_name)s" etc., see db/base.py) doesn't
    # re-template them — passing a bare string here double-prefixes instead.
    op.create_foreign_key(
        op.f("fk_ingest_jobs_source_material_version_id_source_material_versions"),
        "ingest_jobs",
        "source_material_versions",
        ["source_material_version_id"],
        ["id"],
    )
    op.create_foreign_key(
        op.f("fk_ingest_jobs_knowledge_document_version_id_knowledge_document_versions"),
        "ingest_jobs",
        "knowledge_document_versions",
        ["knowledge_document_version_id"],
        ["id"],
    )
    op.create_index(
        op.f("ix_ingest_jobs_source_material_version_id"),
        "ingest_jobs",
        ["source_material_version_id"],
    )
    op.create_index(
        op.f("ix_ingest_jobs_knowledge_document_version_id"),
        "ingest_jobs",
        ["knowledge_document_version_id"],
    )
    op.create_check_constraint(
        op.f("ck_ingest_jobs_exactly_one_target"),
        "ingest_jobs",
        "(source_material_version_id IS NOT NULL) != (knowledge_document_version_id IS NOT NULL)",
    )

    # The original migration (b2c3d4e5f6a7) named this constraint via a bare
    # CheckConstraint(name=...) inside op.create_table(), which — same root cause as
    # op.create_check_constraint()/op.drop_constraint() elsewhere in this history —
    # gets re-templated against target_metadata's naming convention (env.py) even
    # though a name was already given, so on a database that only ever ran forward
    # migrations it's actually stored double-prefixed as
    # "ck_ingest_jobs_ck_ingest_jobs_target_kind". This predates this migration and
    # affects most named CHECK constraints schema-wide; fixing it everywhere is out
    # of scope here. But this migration's own downgrade() recreates the constraint
    # under its *correct* name (via op.create_check_constraint + op.f(), which does
    # not have this bug), so upgrade() must tolerate either name depending on whether
    # this environment has been downgraded-then-upgraded before. DROP CONSTRAINT IF
    # EXISTS on both candidates, rather than a single op.drop_constraint, keeps
    # upgrade()/downgrade() round-trippable regardless of starting state.
    op.execute("ALTER TABLE ingest_jobs DROP CONSTRAINT IF EXISTS ck_ingest_jobs_target_kind")
    op.execute(
        "ALTER TABLE ingest_jobs DROP CONSTRAINT IF EXISTS "
        "ck_ingest_jobs_ck_ingest_jobs_target_kind"
    )
    op.drop_index(op.f("ix_ingest_jobs_target_kind"), table_name="ingest_jobs")
    op.drop_index(op.f("ix_ingest_jobs_target_id"), table_name="ingest_jobs")
    op.drop_column("ingest_jobs", "target_kind")
    op.drop_column("ingest_jobs", "target_id")


def downgrade() -> None:
    op.add_column("ingest_jobs", sa.Column("target_kind", sa.String(length=50), nullable=True))
    op.add_column("ingest_jobs", sa.Column("target_id", sa.Uuid(), nullable=True))

    op.execute(
        "UPDATE ingest_jobs SET target_kind = 'source_material_version', "
        "target_id = source_material_version_id "
        "WHERE source_material_version_id IS NOT NULL"
    )
    op.execute(
        "UPDATE ingest_jobs SET target_kind = 'knowledge_document_version', "
        "target_id = knowledge_document_version_id "
        "WHERE knowledge_document_version_id IS NOT NULL"
    )

    op.alter_column("ingest_jobs", "target_kind", nullable=False)
    op.alter_column("ingest_jobs", "target_id", nullable=False)

    op.create_check_constraint(
        op.f("ck_ingest_jobs_target_kind"),
        "ingest_jobs",
        "target_kind IN ('source_material_version', 'knowledge_document_version')",
    )
    op.create_index(op.f("ix_ingest_jobs_target_kind"), "ingest_jobs", ["target_kind"])
    op.create_index(op.f("ix_ingest_jobs_target_id"), "ingest_jobs", ["target_id"])

    op.drop_constraint(op.f("ck_ingest_jobs_exactly_one_target"), "ingest_jobs", type_="check")
    op.drop_index(op.f("ix_ingest_jobs_knowledge_document_version_id"), table_name="ingest_jobs")
    op.drop_index(op.f("ix_ingest_jobs_source_material_version_id"), table_name="ingest_jobs")
    op.drop_constraint(
        op.f("fk_ingest_jobs_knowledge_document_version_id_knowledge_document_versions"),
        "ingest_jobs",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_ingest_jobs_source_material_version_id_source_material_versions"),
        "ingest_jobs",
        type_="foreignkey",
    )
    op.drop_column("ingest_jobs", "knowledge_document_version_id")
    op.drop_column("ingest_jobs", "source_material_version_id")

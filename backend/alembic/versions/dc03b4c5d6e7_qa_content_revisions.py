"""QA content revisions, lesson section snapshots, and rewrite_content jobs.

Revision ID: dc03b4c5d6e7
Revises: dbf2a3b4c5d6
Create Date: 2026-09-13 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str | Sequence[str] | None = "dc03b4c5d6e7"
down_revision: str | Sequence[str] | None = "dbf2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_generation_lesson_sections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("outline_node_id", sa.Uuid(), nullable=False),
        sa.Column("heading", sa.String(length=200), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["content_generation_runs.id"],
            name=op.f("fk_content_generation_lesson_sections_run_id_content_generation_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["outline_node_id"],
            ["content_generation_outline_nodes.id"],
            name=op.f(
                "fk_content_generation_lesson_sections_outline_node_id_content_generation_outline_nodes"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_content_generation_lesson_sections")),
        sa.UniqueConstraint(
            "run_id",
            "outline_node_id",
            name="uq_content_generation_lesson_sections_run_outline_node",
        ),
    )
    op.create_index(
        op.f("ix_content_generation_lesson_sections_run_id"),
        "content_generation_lesson_sections",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_content_generation_lesson_sections_outline_node_id"),
        "content_generation_lesson_sections",
        ["outline_node_id"],
        unique=False,
    )

    op.create_table(
        "generation_lesson_section_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("section_key", sa.Uuid(), nullable=False),
        sa.Column("heading", sa.String(length=200), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"],
            ["generation_revisions.id"],
            name=op.f("fk_generation_lesson_section_snapshots_revision_id_generation_revisions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_generation_lesson_section_snapshots")),
        sa.UniqueConstraint(
            "revision_id",
            "section_key",
            name="uq_generation_lesson_section_snapshots_revision_section_key",
        ),
    )
    op.create_index(
        op.f("ix_generation_lesson_section_snapshots_revision_id"),
        "generation_lesson_section_snapshots",
        ["revision_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_generation_lesson_section_snapshots_section_key"),
        "generation_lesson_section_snapshots",
        ["section_key"],
        unique=False,
    )
    op.create_index(
        "uq_generation_jobs_one_in_flight_rewrite_content",
        "generation_jobs",
        ["run_id", "kind"],
        unique=True,
        postgresql_where=sa.text("kind = 'rewrite_content' AND status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("uq_generation_jobs_one_in_flight_rewrite_content", table_name="generation_jobs")
    op.drop_index(
        op.f("ix_generation_lesson_section_snapshots_section_key"),
        table_name="generation_lesson_section_snapshots",
    )
    op.drop_index(
        op.f("ix_generation_lesson_section_snapshots_revision_id"),
        table_name="generation_lesson_section_snapshots",
    )
    op.drop_table("generation_lesson_section_snapshots")
    op.drop_index(
        op.f("ix_content_generation_lesson_sections_outline_node_id"),
        table_name="content_generation_lesson_sections",
    )
    op.drop_index(
        op.f("ix_content_generation_lesson_sections_run_id"),
        table_name="content_generation_lesson_sections",
    )
    op.drop_table("content_generation_lesson_sections")

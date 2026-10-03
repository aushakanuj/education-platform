"""ADK curriculum generation jobs and question item_kind.

Revision ID: de25d6e7f8a9
Revises: dd14c5d6e7f8
Create Date: 2026-09-14 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str | Sequence[str] | None = "de25d6e7f8a9"
down_revision: str | Sequence[str] | None = "dd14c5d6e7f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "question_versions",
        sa.Column("item_kind", sa.String(length=16), nullable=True),
    )
    op.create_check_constraint(
        "ck_question_versions_item_kind",
        "question_versions",
        "item_kind IS NULL OR item_kind IN ('theory', 'problem')",
    )
    op.create_table(
        "curriculum_generation_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subtopic_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("transcript", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("reviewer_notes", sa.Text(), nullable=True),
        sa.Column("round_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_material_version_id", sa.Uuid(), nullable=True),
        sa.Column("quiz_version_id", sa.Uuid(), nullable=True),
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
            ["subtopic_id"],
            ["subtopics.id"],
            name=op.f("fk_curriculum_generation_jobs_subtopic_id_subtopics"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_curriculum_generation_jobs_created_by_users"),
        ),
        sa.ForeignKeyConstraint(
            ["source_material_version_id"],
            ["source_material_versions.id"],
            name=op.f(
                "fk_curriculum_generation_jobs_source_material_version_id_source_material_versions"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["quiz_version_id"],
            ["quiz_versions.id"],
            name=op.f("fk_curriculum_generation_jobs_quiz_version_id_quiz_versions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_curriculum_generation_jobs")),
    )
    op.create_index(
        op.f("ix_curriculum_generation_jobs_subtopic_id"),
        "curriculum_generation_jobs",
        ["subtopic_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_curriculum_generation_jobs_created_by"),
        "curriculum_generation_jobs",
        ["created_by"],
        unique=False,
    )
    op.create_index(
        "ix_curriculum_generation_jobs_status_created_at",
        "curriculum_generation_jobs",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_curriculum_generation_jobs_one_in_flight_subtopic",
        "curriculum_generation_jobs",
        ["subtopic_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_curriculum_generation_jobs_one_in_flight_subtopic",
        table_name="curriculum_generation_jobs",
    )
    op.drop_index(
        "ix_curriculum_generation_jobs_status_created_at",
        table_name="curriculum_generation_jobs",
    )
    op.drop_index(
        op.f("ix_curriculum_generation_jobs_created_by"),
        table_name="curriculum_generation_jobs",
    )
    op.drop_index(
        op.f("ix_curriculum_generation_jobs_subtopic_id"),
        table_name="curriculum_generation_jobs",
    )
    op.drop_table("curriculum_generation_jobs")
    op.drop_constraint("ck_question_versions_item_kind", "question_versions", type_="check")
    op.drop_column("question_versions", "item_kind")

"""Topic-grain generation runs and source_materials topic XOR.

Revision ID: d8e9f0a1b2c3
Revises: d7e8f9a0b1c2
Create Date: 2026-09-09 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str | Sequence[str] | None = "d8e9f0a1b2c3"
down_revision: str | Sequence[str] | None = "d7e8f9a0b1c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_IN_FLIGHT_PHASES = (
    "indexing",
    "outlining",
    "outline_review",
    "generating",
    "qa_review",
)


def upgrade() -> None:
    op.drop_index(
        "uq_source_material_versions_one_in_flight_proposal",
        table_name="source_material_versions",
    )

    with op.batch_alter_table("source_materials") as batch_op:
        batch_op.drop_constraint("uq_source_materials_subtopic_slug", type_="unique")
        batch_op.add_column(sa.Column("topic_id", sa.Uuid(), nullable=True))
        batch_op.alter_column("subtopic_id", existing_type=sa.Uuid(), nullable=True)
        batch_op.create_foreign_key(
            op.f("fk_source_materials_topic_id_topics"),
            "topics",
            ["topic_id"],
            ["id"],
        )
        batch_op.create_index(
            op.f("ix_source_materials_topic_id"),
            ["topic_id"],
            unique=False,
        )
        batch_op.create_check_constraint(
            "ck_source_materials_exactly_one_parent",
            "(topic_id IS NOT NULL AND subtopic_id IS NULL) OR "
            "(topic_id IS NULL AND subtopic_id IS NOT NULL)",
        )

    op.create_index(
        "uq_source_materials_subtopic_slug",
        "source_materials",
        ["subtopic_id", "slug"],
        unique=True,
        postgresql_where=sa.text("subtopic_id IS NOT NULL"),
    )
    op.create_index(
        "uq_source_materials_topic_slug",
        "source_materials",
        ["topic_id", "slug"],
        unique=True,
        postgresql_where=sa.text("topic_id IS NOT NULL"),
    )

    op.create_table(
        "content_generation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.Column("submitted_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("target_item_count", sa.Integer(), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("intake_source_material_version_id", sa.Uuid(), nullable=True),
        sa.Column("draft_quiz_version_id", sa.Uuid(), nullable=True),
        sa.Column("draft_lesson_markdown", sa.Text(), nullable=True),
        sa.Column("published_lesson_version_id", sa.Uuid(), nullable=True),
        sa.Column("published_quiz_version_id", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint(
            "target_item_count >= 60 AND target_item_count <= 80",
            name="ck_content_generation_runs_target_item_count",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topics.id"],
            name=op.f("fk_content_generation_runs_topic_id_topics"),
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by_user_id"],
            ["users.id"],
            name=op.f("fk_content_generation_runs_submitted_by_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["intake_source_material_version_id"],
            ["source_material_versions.id"],
            name=op.f(
                "fk_content_generation_runs_intake_source_material_version_id_source_material_versions"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["draft_quiz_version_id"],
            ["quiz_versions.id"],
            name=op.f("fk_content_generation_runs_draft_quiz_version_id_quiz_versions"),
        ),
        sa.ForeignKeyConstraint(
            ["published_lesson_version_id"],
            ["source_material_versions.id"],
            name=op.f(
                "fk_content_generation_runs_published_lesson_version_id_source_material_versions"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["published_quiz_version_id"],
            ["quiz_versions.id"],
            name=op.f("fk_content_generation_runs_published_quiz_version_id_quiz_versions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_content_generation_runs")),
    )
    op.create_index(
        op.f("ix_content_generation_runs_topic_id"),
        "content_generation_runs",
        ["topic_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_content_generation_runs_submitted_by_user_id"),
        "content_generation_runs",
        ["submitted_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_content_generation_runs_phase"),
        "content_generation_runs",
        ["phase"],
        unique=False,
    )
    op.create_index(
        op.f("ix_content_generation_runs_intake_source_material_version_id"),
        "content_generation_runs",
        ["intake_source_material_version_id"],
        unique=False,
    )
    op.create_index(
        "uq_content_generation_runs_one_in_flight_topic",
        "content_generation_runs",
        ["topic_id"],
        unique=True,
        postgresql_where=sa.text(
            "phase IN (" + ", ".join(f"'{p}'" for p in _IN_FLIGHT_PHASES) + ")"
        ),
    )

    op.create_table(
        "content_generation_outline_nodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("token_mass", sa.Integer(), nullable=False),
        sa.Column("prerequisite_score", sa.Numeric(8, 6), nullable=False),
        sa.Column("centrality", sa.Numeric(8, 6), nullable=False),
        sa.Column("weight", sa.Numeric(18, 8), nullable=False),
        sa.Column("quota", sa.Integer(), nullable=True),
        sa.Column("matched_subtopic_id", sa.Uuid(), nullable=True),
        sa.Column("force_create", sa.Boolean(), nullable=False),
        sa.Column("accepted_subtopic_id", sa.Uuid(), nullable=True),
        sa.Column("proposed_outcomes", sa.JSON(), nullable=False),
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
            name=op.f("fk_content_generation_outline_nodes_run_id_content_generation_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["content_generation_outline_nodes.id"],
            name=op.f(
                "fk_content_generation_outline_nodes_parent_id_content_generation_outline_nodes"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["matched_subtopic_id"],
            ["subtopics.id"],
            name=op.f("fk_content_generation_outline_nodes_matched_subtopic_id_subtopics"),
        ),
        sa.ForeignKeyConstraint(
            ["accepted_subtopic_id"],
            ["subtopics.id"],
            name=op.f("fk_content_generation_outline_nodes_accepted_subtopic_id_subtopics"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_content_generation_outline_nodes")),
        sa.UniqueConstraint(
            "run_id",
            "slug",
            name="uq_content_generation_outline_nodes_run_id_slug",
        ),
    )
    op.create_index(
        op.f("ix_content_generation_outline_nodes_run_id"),
        "content_generation_outline_nodes",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_content_generation_outline_nodes_parent_id"),
        "content_generation_outline_nodes",
        ["parent_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_content_generation_outline_nodes_matched_subtopic_id"),
        "content_generation_outline_nodes",
        ["matched_subtopic_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_content_generation_outline_nodes_accepted_subtopic_id"),
        "content_generation_outline_nodes",
        ["accepted_subtopic_id"],
        unique=False,
    )

    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
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
            name=op.f("fk_generation_jobs_run_id_content_generation_runs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_generation_jobs")),
    )
    op.create_index(
        op.f("ix_generation_jobs_run_id"),
        "generation_jobs",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_generation_jobs_status_created_at",
        "generation_jobs",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_generation_jobs_one_in_flight_outline",
        "generation_jobs",
        ["run_id", "kind"],
        unique=True,
        postgresql_where=sa.text("kind = 'outline' AND status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("uq_generation_jobs_one_in_flight_outline", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_status_created_at", table_name="generation_jobs")
    op.drop_index(op.f("ix_generation_jobs_run_id"), table_name="generation_jobs")
    op.drop_table("generation_jobs")

    op.drop_index(
        op.f("ix_content_generation_outline_nodes_accepted_subtopic_id"),
        table_name="content_generation_outline_nodes",
    )
    op.drop_index(
        op.f("ix_content_generation_outline_nodes_matched_subtopic_id"),
        table_name="content_generation_outline_nodes",
    )
    op.drop_index(
        op.f("ix_content_generation_outline_nodes_parent_id"),
        table_name="content_generation_outline_nodes",
    )
    op.drop_index(
        op.f("ix_content_generation_outline_nodes_run_id"),
        table_name="content_generation_outline_nodes",
    )
    op.drop_table("content_generation_outline_nodes")

    op.drop_index(
        "uq_content_generation_runs_one_in_flight_topic",
        table_name="content_generation_runs",
    )
    op.drop_index(
        op.f("ix_content_generation_runs_intake_source_material_version_id"),
        table_name="content_generation_runs",
    )
    op.drop_index(op.f("ix_content_generation_runs_phase"), table_name="content_generation_runs")
    op.drop_index(
        op.f("ix_content_generation_runs_submitted_by_user_id"),
        table_name="content_generation_runs",
    )
    op.drop_index(op.f("ix_content_generation_runs_topic_id"), table_name="content_generation_runs")
    op.drop_table("content_generation_runs")

    op.drop_index("uq_source_materials_topic_slug", table_name="source_materials")
    op.drop_index("uq_source_materials_subtopic_slug", table_name="source_materials")

    with op.batch_alter_table("source_materials") as batch_op:
        batch_op.drop_constraint("ck_source_materials_exactly_one_parent", type_="check")
        batch_op.drop_index(op.f("ix_source_materials_topic_id"))
        batch_op.drop_constraint(op.f("fk_source_materials_topic_id_topics"), type_="foreignkey")
        batch_op.drop_column("topic_id")
        batch_op.alter_column("subtopic_id", existing_type=sa.Uuid(), nullable=False)
        batch_op.create_unique_constraint(
            "uq_source_materials_subtopic_slug",
            ["subtopic_id", "slug"],
        )

    op.create_index(
        "uq_source_material_versions_one_in_flight_proposal",
        "source_material_versions",
        ["source_material_id"],
        unique=True,
        postgresql_where=sa.text(
            "submitted_by_user_id IS NOT NULL AND "
            "lifecycle_status IN ('processing', 'awaiting_approval')"
        ),
    )

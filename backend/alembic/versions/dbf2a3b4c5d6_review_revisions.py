"""Frozen outline revisions and teacher review rounds.

Revision ID: dbf2a3b4c5d6
Revises: dae1f2a3b4c5
Create Date: 2026-09-13 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str | Sequence[str] | None = "dbf2a3b4c5d6"
down_revision: str | Sequence[str] | None = "dae1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "generation_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("stage", sa.String(length=16), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("parent_revision_id", sa.Uuid(), nullable=True),
        sa.Column("origin", sa.String(length=32), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_job_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_model", sa.String(length=100), nullable=True),
        sa.Column("source_round_id", sa.Uuid(), nullable=True),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
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
        sa.CheckConstraint("number >= 1", name="ck_generation_revisions_number"),
        sa.CheckConstraint(
            "(created_by_user_id IS NOT NULL AND created_by_job_id IS NULL) OR "
            "(created_by_user_id IS NULL AND created_by_job_id IS NOT NULL)",
            name="ck_generation_revisions_one_author",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["content_generation_runs.id"],
            name=op.f("fk_generation_revisions_run_id_content_generation_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_revision_id"],
            ["generation_revisions.id"],
            name=op.f("fk_generation_revisions_parent_revision_id_generation_revisions"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_generation_revisions_created_by_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_generation_revisions")),
        sa.UniqueConstraint(
            "run_id",
            "stage",
            "number",
            name="uq_generation_revisions_run_stage_number",
        ),
        sa.UniqueConstraint(
            "parent_revision_id", name="uq_generation_revisions_parent_revision_id"
        ),
    )
    op.create_index(
        op.f("ix_generation_revisions_run_id"), "generation_revisions", ["run_id"], unique=False
    )
    op.create_index(
        op.f("ix_generation_revisions_created_by_user_id"),
        "generation_revisions",
        ["created_by_user_id"],
        unique=False,
    )

    op.create_table(
        "generation_outline_revision_nodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("node_key", sa.Uuid(), nullable=False),
        sa.Column("parent_node_key", sa.Uuid(), nullable=True),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("token_mass", sa.Integer(), nullable=False),
        sa.Column("prerequisite_score", sa.Numeric(8, 6), nullable=False),
        sa.Column("centrality", sa.Numeric(8, 6), nullable=False),
        sa.Column("weight", sa.Numeric(18, 8), nullable=False),
        sa.Column("matched_subtopic_id", sa.Uuid(), nullable=True),
        sa.Column("force_create", sa.Boolean(), nullable=False),
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
            ["revision_id"],
            ["generation_revisions.id"],
            name=op.f("fk_generation_outline_revision_nodes_revision_id_generation_revisions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["matched_subtopic_id"],
            ["subtopics.id"],
            name=op.f("fk_generation_outline_revision_nodes_matched_subtopic_id_subtopics"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_generation_outline_revision_nodes")),
        sa.UniqueConstraint(
            "revision_id",
            "node_key",
            name="uq_generation_outline_revision_nodes_revision_node_key",
        ),
        sa.UniqueConstraint(
            "revision_id",
            "slug",
            name="uq_generation_outline_revision_nodes_revision_slug",
        ),
    )
    op.create_index(
        op.f("ix_generation_outline_revision_nodes_revision_id"),
        "generation_outline_revision_nodes",
        ["revision_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_generation_outline_revision_nodes_node_key"),
        "generation_outline_revision_nodes",
        ["node_key"],
        unique=False,
    )

    op.create_table(
        "review_rounds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("stage", sa.String(length=16), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sealed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("number IN (1, 2)", name="ck_review_rounds_number"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["content_generation_runs.id"],
            name=op.f("fk_review_rounds_run_id_content_generation_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"],
            ["generation_revisions.id"],
            name=op.f("fk_review_rounds_revision_id_generation_revisions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_rounds")),
        sa.UniqueConstraint("run_id", "stage", "number", name="uq_review_rounds_run_stage_number"),
        sa.UniqueConstraint("revision_id", name="uq_review_rounds_revision_id"),
    )
    op.create_index(op.f("ix_review_rounds_run_id"), "review_rounds", ["run_id"], unique=False)
    op.create_index(
        op.f("ix_review_rounds_revision_id"), "review_rounds", ["revision_id"], unique=False
    )
    op.create_index(
        "uq_review_rounds_one_open_per_run",
        "review_rounds",
        ["run_id"],
        unique=True,
        postgresql_where=sa.text("sealed_at IS NULL"),
    )

    op.create_table(
        "review_round_participants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("round_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_user_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("teaching_assignment_ids", sa.JSON(), nullable=False),
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
            ["round_id"],
            ["review_rounds.id"],
            name=op.f("fk_review_round_participants_round_id_review_rounds"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_user_id"],
            ["users.id"],
            name=op.f("fk_review_round_participants_reviewer_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_round_participants")),
        sa.UniqueConstraint(
            "round_id",
            "reviewer_user_id",
            name="uq_review_round_participants_round_reviewer",
        ),
    )
    op.create_index(
        op.f("ix_review_round_participants_round_id"),
        "review_round_participants",
        ["round_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_review_round_participants_reviewer_user_id"),
        "review_round_participants",
        ["reviewer_user_id"],
        unique=False,
    )

    op.create_table(
        "review_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("round_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_user_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
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
            "verdict IN ('approve', 'changes_requested')",
            name="ck_review_decisions_verdict",
        ),
        sa.ForeignKeyConstraint(
            ["round_id"],
            ["review_rounds.id"],
            name=op.f("fk_review_decisions_round_id_review_rounds"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_user_id"],
            ["users.id"],
            name=op.f("fk_review_decisions_reviewer_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"],
            ["generation_revisions.id"],
            name=op.f("fk_review_decisions_revision_id_generation_revisions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_decisions")),
        sa.UniqueConstraint(
            "round_id",
            "reviewer_user_id",
            name="uq_review_decisions_round_reviewer",
        ),
    )
    op.create_index(
        op.f("ix_review_decisions_round_id"), "review_decisions", ["round_id"], unique=False
    )
    op.create_index(
        op.f("ix_review_decisions_reviewer_user_id"),
        "review_decisions",
        ["reviewer_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_review_decisions_revision_id"),
        "review_decisions",
        ["revision_id"],
        unique=False,
    )

    op.create_table(
        "generation_change_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("decision_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("target_kind", sa.String(length=32), nullable=False),
        sa.Column("node_key", sa.Uuid(), nullable=True),
        sa.Column("field", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
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
            ["decision_id"],
            ["review_decisions.id"],
            name=op.f("fk_generation_change_requests_decision_id_review_decisions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"],
            ["generation_revisions.id"],
            name=op.f("fk_generation_change_requests_revision_id_generation_revisions"),
        ),
        sa.ForeignKeyConstraint(
            ["author_user_id"],
            ["users.id"],
            name=op.f("fk_generation_change_requests_author_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_generation_change_requests")),
    )
    op.create_index(
        op.f("ix_generation_change_requests_decision_id"),
        "generation_change_requests",
        ["decision_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_generation_change_requests_revision_id"),
        "generation_change_requests",
        ["revision_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_generation_change_requests_author_user_id"),
        "generation_change_requests",
        ["author_user_id"],
        unique=False,
    )

    op.create_table(
        "review_round_closures",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("round_id", sa.Uuid(), nullable=False),
        sa.Column("base_revision_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("collated_request_ids", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
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
            ["round_id"],
            ["review_rounds.id"],
            name=op.f("fk_review_round_closures_round_id_review_rounds"),
        ),
        sa.ForeignKeyConstraint(
            ["base_revision_id"],
            ["generation_revisions.id"],
            name=op.f("fk_review_round_closures_base_revision_id_generation_revisions"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_review_round_closures_actor_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_round_closures")),
        sa.UniqueConstraint("round_id", name="uq_review_round_closures_round_id"),
    )
    op.create_index(
        op.f("ix_review_round_closures_round_id"),
        "review_round_closures",
        ["round_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_review_round_closures_actor_user_id"),
        "review_round_closures",
        ["actor_user_id"],
        unique=False,
    )

    op.add_column("generation_jobs", sa.Column("close_record_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_generation_jobs_close_record_id_review_round_closures"),
        "generation_jobs",
        "review_round_closures",
        ["close_record_id"],
        ["id"],
    )
    op.create_index(
        "uq_generation_jobs_close_record_id",
        "generation_jobs",
        ["close_record_id"],
        unique=True,
        postgresql_where=sa.text("close_record_id IS NOT NULL"),
    )
    op.create_index(
        "uq_generation_jobs_one_in_flight_rewrite_outline",
        "generation_jobs",
        ["run_id", "kind"],
        unique=True,
        postgresql_where=sa.text("kind = 'rewrite_outline' AND status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("uq_generation_jobs_one_in_flight_rewrite_outline", table_name="generation_jobs")
    op.drop_index("uq_generation_jobs_close_record_id", table_name="generation_jobs")
    op.drop_constraint(
        op.f("fk_generation_jobs_close_record_id_review_round_closures"),
        "generation_jobs",
        type_="foreignkey",
    )
    op.drop_column("generation_jobs", "close_record_id")
    op.drop_index(
        op.f("ix_review_round_closures_actor_user_id"), table_name="review_round_closures"
    )
    op.drop_index(op.f("ix_review_round_closures_round_id"), table_name="review_round_closures")
    op.drop_table("review_round_closures")
    op.drop_index(
        op.f("ix_generation_change_requests_author_user_id"),
        table_name="generation_change_requests",
    )
    op.drop_index(
        op.f("ix_generation_change_requests_revision_id"),
        table_name="generation_change_requests",
    )
    op.drop_index(
        op.f("ix_generation_change_requests_decision_id"),
        table_name="generation_change_requests",
    )
    op.drop_table("generation_change_requests")
    op.drop_index(op.f("ix_review_decisions_revision_id"), table_name="review_decisions")
    op.drop_index(op.f("ix_review_decisions_reviewer_user_id"), table_name="review_decisions")
    op.drop_index(op.f("ix_review_decisions_round_id"), table_name="review_decisions")
    op.drop_table("review_decisions")
    op.drop_index(
        op.f("ix_review_round_participants_reviewer_user_id"),
        table_name="review_round_participants",
    )
    op.drop_index(
        op.f("ix_review_round_participants_round_id"), table_name="review_round_participants"
    )
    op.drop_table("review_round_participants")
    op.drop_index("uq_review_rounds_one_open_per_run", table_name="review_rounds")
    op.drop_index(op.f("ix_review_rounds_revision_id"), table_name="review_rounds")
    op.drop_index(op.f("ix_review_rounds_run_id"), table_name="review_rounds")
    op.drop_table("review_rounds")
    op.drop_index(
        op.f("ix_generation_outline_revision_nodes_node_key"),
        table_name="generation_outline_revision_nodes",
    )
    op.drop_index(
        op.f("ix_generation_outline_revision_nodes_revision_id"),
        table_name="generation_outline_revision_nodes",
    )
    op.drop_table("generation_outline_revision_nodes")
    op.drop_index(
        op.f("ix_generation_revisions_created_by_user_id"), table_name="generation_revisions"
    )
    op.drop_index(op.f("ix_generation_revisions_run_id"), table_name="generation_revisions")
    op.drop_table("generation_revisions")

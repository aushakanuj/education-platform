"""Rationale columns on answer keys and one in-flight items job per run.

Revision ID: d9e0f1a2b3c4
Revises: d8e9f0a1b2c3
Create Date: 2026-09-12 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str | Sequence[str] | None = "d9e0f1a2b3c4"
down_revision: str | Sequence[str] | None = "d8e9f0a1b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("question_answer_keys") as batch_op:
        batch_op.add_column(sa.Column("correct_rationale", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("distractor_rationales", sa.JSON(), nullable=True))

    op.create_index(
        "uq_generation_jobs_one_in_flight_items",
        "generation_jobs",
        ["run_id", "kind"],
        unique=True,
        postgresql_where=sa.text("kind = 'items' AND status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("uq_generation_jobs_one_in_flight_items", table_name="generation_jobs")
    with op.batch_alter_table("question_answer_keys") as batch_op:
        batch_op.drop_column("distractor_rationales")
        batch_op.drop_column("correct_rationale")

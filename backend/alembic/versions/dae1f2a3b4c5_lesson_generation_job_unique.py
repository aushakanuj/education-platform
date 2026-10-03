"""One in-flight lesson generation job per run.

Revision ID: dae1f2a3b4c5
Revises: d9e0f1a2b3c4
Create Date: 2026-09-12 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str | Sequence[str] | None = "dae1f2a3b4c5"
down_revision: str | Sequence[str] | None = "d9e0f1a2b3c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_generation_jobs_one_in_flight_lesson",
        "generation_jobs",
        ["run_id", "kind"],
        unique=True,
        postgresql_where=sa.text("kind = 'lesson' AND status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("uq_generation_jobs_one_in_flight_lesson", table_name="generation_jobs")

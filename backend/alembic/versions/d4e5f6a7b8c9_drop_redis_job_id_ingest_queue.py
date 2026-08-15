"""Drop redis_job_id; add (status, created_at) index for claim queries.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-15 11:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("ingest_jobs", "redis_job_id")
    op.create_index(
        "ix_ingest_jobs_status_created_at",
        "ingest_jobs",
        ["status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ingest_jobs_status_created_at", table_name="ingest_jobs")
    op.add_column(
        "ingest_jobs",
        sa.Column("redis_job_id", sa.String(length=100), nullable=True),
    )

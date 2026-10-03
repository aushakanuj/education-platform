"""Lease columns so workers can reclaim jobs left stuck in running.

Revision ID: e8f9a0b1c2d3
Revises: de25d6e7f8a9
Create Date: 2026-09-24 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str | Sequence[str] | None = "e8f9a0b1c2d3"
down_revision: str | Sequence[str] | None = "de25d6e7f8a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("generation_jobs", "ingest_jobs", "curriculum_generation_jobs")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        )
        op.add_column(
            table,
            sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        )
        op.add_column(table, sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "locked_until")
        op.drop_column(table, "max_attempts")
        op.drop_column(table, "attempts")

"""Teacher lesson proposals: submitter column, in-flight unique, awaiting markdown.

Revision ID: d7e8f9a0b1c2
Revises: a352c5d4a076
Create Date: 2026-09-09 00:00:00.000000

`awaiting_approval` is a Python/SQLAlchemy enum value stored as VARCHAR
(`native_enum=False`). No Postgres ALTER TYPE.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str | Sequence[str] | None = "d7e8f9a0b1c2"
down_revision: str | Sequence[str] | None = "a352c5d4a076"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "source_material_versions",
        "lifecycle_status",
        existing_type=sa.String(length=10),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
    op.add_column(
        "source_material_versions",
        sa.Column("submitted_by_user_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        op.f("ix_source_material_versions_submitted_by_user_id"),
        "source_material_versions",
        ["submitted_by_user_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_source_material_versions_submitted_by_user_id_users"),
        "source_material_versions",
        "users",
        ["submitted_by_user_id"],
        ["id"],
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
    op.create_check_constraint(
        "ck_source_material_versions_awaiting_has_markdown",
        "source_material_versions",
        "(lifecycle_status <> 'awaiting_approval') OR "
        "(content_markdown IS NOT NULL AND length(content_markdown) > 0)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_source_material_versions_awaiting_has_markdown",
        "source_material_versions",
        type_="check",
    )
    op.drop_index(
        "uq_source_material_versions_one_in_flight_proposal",
        table_name="source_material_versions",
    )
    op.drop_constraint(
        op.f("fk_source_material_versions_submitted_by_user_id_users"),
        "source_material_versions",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_source_material_versions_submitted_by_user_id"),
        table_name="source_material_versions",
    )
    op.drop_column("source_material_versions", "submitted_by_user_id")
    op.alter_column(
        "source_material_versions",
        "lifecycle_status",
        existing_type=sa.String(length=32),
        type_=sa.String(length=10),
        existing_nullable=False,
    )

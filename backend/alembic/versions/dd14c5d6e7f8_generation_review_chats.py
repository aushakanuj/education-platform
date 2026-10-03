"""Generation review chat tables owned by the run, not policy conversations.

Revision ID: dd14c5d6e7f8
Revises: dc03b4c5d6e7
Create Date: 2026-09-13 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str | Sequence[str] | None = "dd14c5d6e7f8"
down_revision: str | Sequence[str] | None = "dc03b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_generation_review_chats",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
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
            name=op.f("fk_content_generation_review_chats_run_id_content_generation_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_content_generation_review_chats_owner_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_content_generation_review_chats")),
        sa.UniqueConstraint(
            "run_id",
            "owner_user_id",
            name="uq_content_generation_review_chats_run_owner",
        ),
    )
    op.create_index(
        op.f("ix_content_generation_review_chats_run_id"),
        "content_generation_review_chats",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_content_generation_review_chats_owner_user_id"),
        "content_generation_review_chats",
        ["owner_user_id"],
        unique=False,
    )
    op.create_table(
        "content_generation_review_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chat_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=True),
        sa.Column("draft_change_request", sa.JSON(), nullable=True),
        sa.Column("token_estimate", sa.Integer(), nullable=False, server_default="0"),
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
            "role IN ('user', 'assistant')",
            name="ck_content_generation_review_messages_role",
        ),
        sa.ForeignKeyConstraint(
            ["chat_id"],
            ["content_generation_review_chats.id"],
            name=op.f(
                "fk_content_generation_review_messages_chat_id_content_generation_review_chats"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_content_generation_review_messages")),
    )
    op.create_index(
        op.f("ix_content_generation_review_messages_chat_id"),
        "content_generation_review_messages",
        ["chat_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_content_generation_review_messages_chat_id"),
        table_name="content_generation_review_messages",
    )
    op.drop_table("content_generation_review_messages")
    op.drop_index(
        op.f("ix_content_generation_review_chats_owner_user_id"),
        table_name="content_generation_review_chats",
    )
    op.drop_index(
        op.f("ix_content_generation_review_chats_run_id"),
        table_name="content_generation_review_chats",
    )
    op.drop_table("content_generation_review_chats")

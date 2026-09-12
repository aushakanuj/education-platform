"""merge heads

Revision ID: a352c5d4a076
Revises: f7a8b9c0d1e2, f8c841992918
Create Date: 2026-09-10 17:29:34.137927
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str | Sequence[str] | None = "a352c5d4a076"
down_revision: str | Sequence[str] | None = ("f7a8b9c0d1e2", "f8c841992918")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

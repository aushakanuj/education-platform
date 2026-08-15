"""Shared SQLAlchemy helpers for the Postgres POC."""

from __future__ import annotations

import enum
from typing import Any

from sqlalchemy import JSON, Enum, Index, text


def str_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    """Store enums as VARCHAR values (portable; avoids native Postgres enums)."""
    return Enum(
        enum_cls,
        name=name,
        values_callable=lambda members: [item.value for item in members],
        native_enum=False,
        validate_strings=True,
    )


def partial_unique_index(name: str, *columns: Any, where: str) -> Index:
    """Unique partial index with a Postgres WHERE clause."""
    return Index(name, *columns, unique=True, postgresql_where=text(where))


JsonDict = JSON

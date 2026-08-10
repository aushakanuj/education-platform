"""sqlite-vec sidecar store for chunk embeddings."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from education_platform.core.config import get_settings
from education_platform.modules.rag.embeddings import embedding_dimensions

_TABLE = "chunk_embeddings"


@dataclass(frozen=True, slots=True)
class VectorRow:
    chunk_id: UUID
    embedding: list[float]
    doc_id: UUID
    doc_kind: str
    institution_id: UUID
    required_roles: list[str]
    doc_type: str | None
    page_number: int | None
    version_id: UUID


def _connect(path: Path | None = None) -> sqlite3.Connection:
    settings = get_settings()
    db_path = path or settings.vector_db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.enable_load_extension(True)
    import sqlite_vec

    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def ensure_schema(path: Path | None = None) -> None:
    dims = embedding_dimensions()
    with _connect(path) as conn:
        conn.execute(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {_TABLE} USING vec0(
              chunk_id TEXT PRIMARY KEY,
              embedding float[{dims}],
              +doc_id TEXT,
              +doc_kind TEXT,
              +institution_id TEXT,
              +required_roles TEXT,
              +doc_type TEXT,
              +page_number INTEGER,
              +version_id TEXT
            )
            """
        )
        conn.commit()


def delete_by_version(version_id: UUID, *, path: Path | None = None) -> int:
    ensure_schema(path)
    with _connect(path) as conn:
        cur = conn.execute(
            f"DELETE FROM {_TABLE} WHERE version_id = ?",
            (str(version_id),),
        )
        conn.commit()
        return int(cur.rowcount or 0)


def upsert_rows(rows: list[VectorRow], *, path: Path | None = None) -> None:
    if not rows:
        return
    ensure_schema(path)
    with _connect(path) as conn:
        for row in rows:
            conn.execute(
                f"DELETE FROM {_TABLE} WHERE chunk_id = ?",
                (str(row.chunk_id),),
            )
            conn.execute(
                f"""
                INSERT INTO {_TABLE}(
                  chunk_id, embedding, doc_id, doc_kind, institution_id,
                  required_roles, doc_type, page_number, version_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(row.chunk_id),
                    _serialize_embedding(row.embedding),
                    str(row.doc_id),
                    row.doc_kind,
                    str(row.institution_id),
                    json.dumps(row.required_roles),
                    row.doc_type,
                    row.page_number,
                    str(row.version_id),
                ),
            )
        conn.commit()


def count_for_version(version_id: UUID, *, path: Path | None = None) -> int:
    ensure_schema(path)
    with _connect(path) as conn:
        cur = conn.execute(
            f"SELECT COUNT(*) FROM {_TABLE} WHERE version_id = ?",
            (str(version_id),),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0


def _serialize_embedding(values: list[float]) -> Any:
    try:
        import sqlite_vec

        return sqlite_vec.serialize_float32(values)
    except Exception:
        # Fallback for environments where serialize helper differs.
        return values

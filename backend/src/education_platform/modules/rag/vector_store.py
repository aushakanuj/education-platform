"""pgvector store for chunk embeddings (same Postgres as relational tables)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import cast, create_engine, delete, func, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.orm import Session

from education_platform.core.config import get_settings
from education_platform.db.url import to_sync_url
from education_platform.modules.rag.contracts import VectorRow
from education_platform.modules.rag.models import ChunkEmbedding

__all__ = [
    "SimilarChunk",
    "VectorRow",
    "count_for_version",
    "delete_by_version",
    "search_similar",
    "upsert_rows",
]


@dataclass(frozen=True, slots=True)
class SimilarChunk:
    chunk_id: UUID
    version_id: UUID
    doc_id: UUID
    doc_kind: str
    distance: float


@contextmanager
def _session() -> Iterator[Session]:
    settings = get_settings()
    engine = create_engine(to_sync_url(settings.database_url), pool_pre_ping=True)
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


def delete_by_version(version_id: UUID) -> int:
    with _session() as session:
        result = session.execute(
            delete(ChunkEmbedding).where(ChunkEmbedding.version_id == version_id)
        )
        session.commit()
        return int(result.rowcount)  # type: ignore[attr-defined]


def upsert_rows(rows: list[VectorRow]) -> None:
    if not rows:
        return
    validated = [VectorRow.model_validate(row) for row in rows]
    with _session() as session:
        for row in validated:
            stmt = insert(ChunkEmbedding).values(
                chunk_id=row.chunk_id,
                embedding=row.embedding,
                doc_id=row.doc_id,
                doc_kind=row.doc_kind,
                institution_id=row.institution_id,
                required_roles=row.required_roles,
                doc_type=row.doc_type,
                page_number=row.page_number,
                version_id=row.version_id,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[ChunkEmbedding.chunk_id],
                set_={
                    "embedding": stmt.excluded.embedding,
                    "doc_id": stmt.excluded.doc_id,
                    "doc_kind": stmt.excluded.doc_kind,
                    "institution_id": stmt.excluded.institution_id,
                    "required_roles": stmt.excluded.required_roles,
                    "doc_type": stmt.excluded.doc_type,
                    "page_number": stmt.excluded.page_number,
                    "version_id": stmt.excluded.version_id,
                },
            )
            session.execute(stmt)
        session.commit()


def count_for_version(version_id: UUID) -> int:
    with _session() as session:
        return int(
            session.scalar(
                select(func.count())
                .select_from(ChunkEmbedding)
                .where(ChunkEmbedding.version_id == version_id)
            )
            or 0
        )


def search_similar(
    query_embedding: list[float],
    *,
    institution_id: UUID,
    limit: int = 10,
    required_role: str | None = None,
    doc_kind: str | None = None,
    doc_type: str | None = None,
) -> list[SimilarChunk]:
    """Exact cosine-distance search (no IVFFlat/HNSW for POC volume)."""
    distance = ChunkEmbedding.embedding.cosine_distance(query_embedding)
    stmt = (
        select(
            ChunkEmbedding.chunk_id,
            ChunkEmbedding.version_id,
            ChunkEmbedding.doc_id,
            ChunkEmbedding.doc_kind,
            distance.label("distance"),
        )
        .where(ChunkEmbedding.institution_id == institution_id)
        .order_by(distance)
        .limit(limit)
    )
    if doc_kind is not None:
        stmt = stmt.where(ChunkEmbedding.doc_kind == doc_kind)
    if doc_type is not None:
        stmt = stmt.where(ChunkEmbedding.doc_type == doc_type)
    if required_role is not None:
        stmt = stmt.where(cast(ChunkEmbedding.required_roles, JSONB).contains([required_role]))

    with _session() as session:
        rows = session.execute(stmt).all()
    return [
        SimilarChunk(
            chunk_id=row.chunk_id,
            version_id=row.version_id,
            doc_id=row.doc_id,
            doc_kind=row.doc_kind,
            distance=float(row.distance),
        )
        for row in rows
    ]

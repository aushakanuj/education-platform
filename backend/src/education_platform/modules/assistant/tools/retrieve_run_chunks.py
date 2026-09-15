"""Run-scoped intake retrieval. Not registered on the policy tool registry."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.modules.materials.models import SourceChunk

_DEFAULT_LIMIT = 8


@dataclass(frozen=True, slots=True)
class RunChunk:
    id: str
    label: str
    excerpt: str
    page_number: int | None


def _score(text: str, query: str) -> int:
    tokens = {token for token in query.lower().split() if len(token) > 2}
    if not tokens:
        return 0
    haystack = text.lower()
    return sum(1 for token in tokens if token in haystack)


async def retrieve_run_chunks(
    session: AsyncSession,
    *,
    intake_version_id: UUID,
    query: str,
    limit: int = _DEFAULT_LIMIT,
) -> tuple[RunChunk, ...]:
    """Return intake SMV chunks for this run only. Never mixes handbook embeddings."""
    rows = (
        await session.scalars(
            select(SourceChunk)
            .where(SourceChunk.source_material_version_id == intake_version_id)
            .order_by(SourceChunk.ordinal)
        )
    ).all()
    if not rows:
        return ()
    ranked = sorted(rows, key=lambda row: _score(row.text, query), reverse=True)
    selected = ranked[: max(1, limit)]
    if all(_score(row.text, query) == 0 for row in selected):
        selected = list(rows[: max(1, limit)])
    chunks: list[RunChunk] = []
    for row in selected:
        excerpt = row.text.strip()[:500]
        if not excerpt:
            continue
        heading = (row.section_heading or "").strip()
        chunks.append(
            RunChunk(
                id=str(row.id),
                label=heading or "Intake PDF",
                excerpt=excerpt,
                page_number=row.page_number,
            )
        )
    return tuple(chunks)

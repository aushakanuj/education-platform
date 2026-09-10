"""Lesson content and learning-outcome seed helpers."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from education_platform.modules.academics.models import LearningOutcome, Subtopic
from education_platform.modules.materials.models import (
    SourceMaterial,
    SourceMaterialStatus,
    SourceMaterialVersion,
    SourceMaterialVersionStatus,
)


def checksum(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def ensure_outcomes(
    session: Session,
    subtopic: Subtopic,
    statements: list[str],
    *,
    display_title: str,
) -> LearningOutcome:
    cleaned = [item.strip() for item in statements if item.strip()]
    if not cleaned:
        cleaned = [f"Demonstrate understanding of {display_title}"]

    primary: LearningOutcome | None = None
    for index, statement in enumerate(cleaned, start=1):
        code = f"LO{index}"
        outcome = session.scalar(
            select(LearningOutcome).where(
                LearningOutcome.subtopic_id == subtopic.id,
                LearningOutcome.code == code,
            )
        )
        if outcome is None:
            outcome = LearningOutcome(
                subtopic_id=subtopic.id,
                code=code,
                statement=statement,
                sequence=index,
            )
            session.add(outcome)
            session.flush()
        else:
            outcome.statement = statement
            outcome.sequence = index
        if primary is None:
            primary = outcome

    assert primary is not None
    return primary


def upsert_material_version(
    session: Session,
    subtopic: Subtopic,
    *,
    title: str,
    markdown: str,
) -> SourceMaterialVersion:
    material = session.scalar(
        select(SourceMaterial).where(
            SourceMaterial.subtopic_id == subtopic.id,
            SourceMaterial.slug == "lesson",
        )
    )
    if material is None:
        material = SourceMaterial(
            subtopic_id=subtopic.id,
            title=title,
            slug="lesson",
            status=SourceMaterialStatus.PUBLISHED,
        )
        session.add(material)
        session.flush()
    else:
        material.title = title
        material.status = SourceMaterialStatus.PUBLISHED

    digest = checksum(markdown)
    published = session.scalar(
        select(SourceMaterialVersion).where(
            SourceMaterialVersion.source_material_id == material.id,
            SourceMaterialVersion.lifecycle_status == SourceMaterialVersionStatus.PUBLISHED,
        )
    )
    if published is not None and published.checksum == digest:
        return published
    if published is not None:
        published.lifecycle_status = SourceMaterialVersionStatus.SUPERSEDED

    next_version = (
        int(
            session.scalar(
                select(func.max(SourceMaterialVersion.version_number)).where(
                    SourceMaterialVersion.source_material_id == material.id
                )
            )
            or 0
        )
        + 1
    )
    version = SourceMaterialVersion(
        source_material_id=material.id,
        version_number=next_version,
        lifecycle_status=SourceMaterialVersionStatus.PUBLISHED,
        title=title,
        content_markdown=markdown,
        content_format="markdown",
        checksum=digest,
        published_at=datetime.now(UTC),
    )
    session.add(version)
    session.flush()
    return version

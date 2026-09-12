"""Small materials lookups shared by materials, assessments, and academics.

These are query helpers, not the materials service — callers may import them without
creating a service-to-service cycle.
"""

from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.modules.academics.models import (
    AcademicPeriod,
    GradeSubjectOffering,
    PeriodGrade,
    Subtopic,
    Topic,
)
from education_platform.modules.authorization.scope import Scope
from education_platform.modules.materials.models import (
    SourceMaterial,
    SourceMaterialVersion,
    SourceMaterialVersionStatus,
    StudentMaterialProgress,
)


async def published_material_version(
    session: AsyncSession, subtopic_id: UUID
) -> SourceMaterialVersion | None:
    return cast(
        SourceMaterialVersion | None,
        await session.scalar(
            select(SourceMaterialVersion)
            .join(SourceMaterial, SourceMaterial.id == SourceMaterialVersion.source_material_id)
            .where(
                SourceMaterial.subtopic_id == subtopic_id,
                SourceMaterialVersion.lifecycle_status == SourceMaterialVersionStatus.PUBLISHED,
            )
            .order_by(SourceMaterialVersion.version_number.desc())
        ),
    )


async def progress_for(
    session: AsyncSession,
    subject_enrollment_id: UUID | None,
    version_id: UUID | None,
) -> StudentMaterialProgress | None:
    if subject_enrollment_id is None or version_id is None:
        return None
    return cast(
        StudentMaterialProgress | None,
        await session.scalar(
            select(StudentMaterialProgress).where(
                StudentMaterialProgress.student_subject_enrollment_id == subject_enrollment_id,
                StudentMaterialProgress.source_material_version_id == version_id,
            )
        ),
    )


async def subtopic_by_slug(
    session: AsyncSession, topic_id: str, *, scope: Scope
) -> Subtopic | None:
    """Resolve a curriculum slug inside the caller's scope.

    Slugs are unique only per topic (`uq_subtopics_topic_slug`). Ambiguous hits return
    None — same as missing — so callers must use a subtopic id when the slug is not unique.
    """
    stmt = (
        select(Subtopic)
        .join(Topic, Topic.id == Subtopic.topic_id)
        .join(
            GradeSubjectOffering,
            GradeSubjectOffering.id == Topic.grade_subject_offering_id,
        )
        .join(PeriodGrade, PeriodGrade.id == GradeSubjectOffering.period_grade_id)
        .join(AcademicPeriod, AcademicPeriod.id == PeriodGrade.academic_period_id)
        .where(
            Subtopic.slug == topic_id,
            AcademicPeriod.institution_id == scope.institution_id,
        )
        .order_by(Subtopic.sequence, Subtopic.id)
    )
    if not scope.unrestricted:
        if not scope.offering_ids:
            return None
        stmt = stmt.where(GradeSubjectOffering.id.in_(scope.offering_ids))
    matches = list(await session.scalars(stmt))
    if len(matches) != 1:
        return None
    return matches[0]

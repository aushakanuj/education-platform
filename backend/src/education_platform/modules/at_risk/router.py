"""At-risk endpoints — staff only (`require_role("teacher", "administrator")`)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.api.deps import Principal, get_scope, require_role
from education_platform.core.errors import DomainError
from education_platform.db.session import get_session
from education_platform.modules.at_risk import service
from education_platform.modules.at_risk.schemas import (
    DismissIn,
    DriverOut,
    FlagListOut,
    FlagOut,
    RecomputeOut,
)
from education_platform.modules.authorization.scope import Scope

router = APIRouter(tags=["at-risk"])

_STAFF_ONLY = require_role("teacher", "administrator")


@router.get("/at-risk/flags", response_model=FlagListOut)
async def list_flags(
    principal: Principal = Depends(_STAFF_ONLY),
    scope: Scope = Depends(get_scope),
    session: AsyncSession = Depends(get_session),
) -> FlagListOut:
    rows = await service.list_flags(session, scope)
    await service.record_flag_view(
        session,
        institution_id=principal.institution_id,
        actor_user_id=principal.user_id,
        rows_returned=len(rows),
    )

    return FlagListOut(
        rows_returned=len(rows),
        items=[
            FlagOut(
                id=row.id,
                student_id=row.student_id,
                student_name=row.student_name,
                grade_subject_offering_id=row.grade_subject_offering_id,
                subject=row.subject,
                tier=row.tier,
                drivers=[DriverOut(**driver) for driver in row.drivers],
                status=row.status,
                dismissed_by_user_id=row.dismissed_by_user_id,
                dismissal_note=row.dismissal_note,
            )
            for row in rows
        ],
    )


@router.post("/at-risk/flags/{flag_id}/dismiss", response_model=FlagOut)
async def dismiss_flag(
    flag_id: UUID,
    body: DismissIn,
    principal: Principal = Depends(_STAFF_ONLY),
    scope: Scope = Depends(get_scope),
    session: AsyncSession = Depends(get_session),
) -> FlagOut:
    result = await service.dismiss_flag(
        session,
        scope,
        flag_id=flag_id,
        actor_user_id=principal.user_id,
        institution_id=principal.institution_id,
        note=body.note,
    )

    if result is None:
        raise DomainError("No such flag", status_code=404)

    return FlagOut(
        id=result.id,
        student_id=result.student_id,
        student_name="",
        grade_subject_offering_id=result.grade_subject_offering_id,
        subject=None,
        tier=result.tier,
        drivers=[DriverOut(**driver) for driver in result.drivers],
        status=result.status,
        dismissed_by_user_id=result.dismissed_by_user_id,
        dismissal_note=result.dismissal_note,
    )


@router.post("/at-risk/recompute", response_model=RecomputeOut)
async def recompute(
    principal: Principal = Depends(require_role("administrator")),
    session: AsyncSession = Depends(get_session),
) -> RecomputeOut:
    result = await service.recompute_institution(session, institution_id=principal.institution_id)
    return RecomputeOut(
        students_considered=result.students_considered,
        flags_active=result.flags_active,
        flags_resolved=result.flags_resolved,
    )

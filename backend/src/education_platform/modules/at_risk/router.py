"""At-risk endpoints. Every route is gated `require_role("teacher", "administrator")`
before the handler runs -- a student must never reach this feature at all, which is a
stronger and simpler guarantee than trusting row-level scoping to always come out empty
for them (spec Section 7.3; see service.py's `list_flags` docstring for why row-level
scoping alone is not enough here)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.api.deps import Principal, get_scope, require_role
from education_platform.db.session import get_session
from education_platform.modules.at_risk import service
from education_platform.modules.authorization.scope import Scope

router = APIRouter(tags=["at-risk"])

_STAFF_ONLY = require_role("teacher", "administrator")


class DriverOut(BaseModel):
    metric: str
    value: float
    comparison: str
    window: str


class FlagOut(BaseModel):
    id: UUID
    student_id: UUID
    student_name: str
    grade_subject_offering_id: UUID | None
    subject: str | None
    tier: str
    drivers: list[DriverOut]
    status: str
    dismissed_by_user_id: UUID | None
    dismissal_note: str | None


class FlagListOut(BaseModel):
    rows_returned: int
    items: list[FlagOut]


@router.get("/at-risk/flags", response_model=FlagListOut)
async def list_flags(
    principal: Principal = Depends(_STAFF_ONLY),
    scope: Scope = Depends(get_scope),
    session: AsyncSession = Depends(get_session),
) -> FlagListOut:
    """Active flags this caller may see: their taught subjects' flags, and -- if they are
    an administrator -- every attendance-only flag too (spec Section 7.2)."""
    rows = await service.list_flags(session, scope)
    await service.record_flag_view(
        session,
        institution_id=principal.institution_id,
        actor_user_id=principal.user_id,
        rows_returned=len(rows),
    )
    await session.commit()

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


class DismissIn(BaseModel):
    note: str | None = None


@router.post("/at-risk/flags/{flag_id}/dismiss", response_model=FlagOut)
async def dismiss_flag(
    flag_id: UUID,
    body: DismissIn,
    principal: Principal = Depends(_STAFF_ONLY),
    scope: Scope = Depends(get_scope),
    session: AsyncSession = Depends(get_session),
) -> FlagOut:
    """AR-4: dismiss a flag. 404, not 403, for a flag outside the caller's scope or one
    that does not exist -- the single-record form of the same rule §7.2 applies to lists."""
    result = await service.dismiss_flag(
        session,
        scope,
        flag_id=flag_id,
        actor_user_id=principal.user_id,
        institution_id=principal.institution_id,
        note=body.note,
    )
    await session.commit()

    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such flag")

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


class RecomputeOut(BaseModel):
    students_considered: int
    flags_active: int
    flags_resolved: int


@router.post("/at-risk/recompute", response_model=RecomputeOut)
async def recompute(
    principal: Principal = Depends(require_role("administrator")),
    session: AsyncSession = Depends(get_session),
) -> RecomputeOut:
    """Recompute every flag in the caller's institution. Administrator-only: this reads
    every student in the school to compute, which is a different, wider action than any
    read a teacher's own Scope would ever permit -- gated on capability, not on Scope,
    for exactly that reason."""
    result = await service.recompute_institution(session, institution_id=principal.institution_id)
    await session.commit()
    return RecomputeOut(
        students_considered=result.students_considered,
        flags_active=result.flags_active,
        flags_resolved=result.flags_resolved,
    )

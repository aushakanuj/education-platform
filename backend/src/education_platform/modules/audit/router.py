"""Administrator-facing audit trail."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.api.deps import Principal, require_administrator
from education_platform.db.session import get_session
from education_platform.modules.audit import service
from education_platform.modules.audit.schemas import AuditEventOut

router = APIRouter(tags=["audit"])


@router.get("/admin/audit-events", response_model=list[AuditEventOut])
async def list_audit_events(
    limit: int = Query(default=100, ge=1, le=500),
    event_type: str | None = Query(default=None),
    principal: Principal = Depends(require_administrator),
    session: AsyncSession = Depends(get_session),
) -> list[AuditEventOut]:
    """Newest first, scoped to the caller's institution."""
    events = await service.list_events(
        session,
        institution_id=principal.institution_id,
        limit=limit,
        event_type=event_type,
    )
    return [AuditEventOut.model_validate(event) for event in events]

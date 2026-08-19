"""Administrator-facing audit trail."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.api.deps import Principal, require_administrator
from education_platform.db.session import get_session
from education_platform.modules.audit import service

router = APIRouter(tags=["audit"])


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    actor_user_id: UUID | None
    event_type: str
    entity_type: str
    entity_id: UUID | None
    payload: dict[str, Any]


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

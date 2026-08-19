"""Write audit events.

The `audit_events` table has existed since the first migration but nothing wrote to it.
This module is the only place that does. The rule from
`docs/design/02-identity-tenancy-and-authorization.md` section 10: an access that returned
nothing because of scope is *more* important to record than one that succeeded, because it
is the evidence that the boundary held.
"""

from __future__ import annotations

import enum
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.modules.auth.models import AuditEvent


class AuditAction(str, enum.Enum):
    """Event types. Keep this list closed so the audit screen can filter reliably."""

    LOGIN = "auth.login"
    LOGIN_FAILED = "auth.login_failed"
    SCOPED_READ = "data.scoped_read"
    ASK_DATA = "data.ask"
    ASK_DOCUMENTS = "documents.ask"
    VIEW_FLAGS = "risk.view_flags"
    RECORD_INTERVENTION = "risk.record_intervention"
    QUIZ_APPROVED = "assessment.quiz_approved"
    QUIZ_SUBMITTED = "assessment.quiz_submitted"
    DOCUMENT_UPLOADED = "documents.uploaded"
    ATTENDANCE_RECORDED = "attendance.recorded"
    PERMISSION_DENIED = "auth.permission_denied"


async def record_event(
    session: AsyncSession,
    *,
    institution_id: UUID,
    event_type: AuditAction | str,
    entity_type: str,
    actor_user_id: UUID | None = None,
    entity_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
    flush: bool = True,
) -> AuditEvent:
    """Append one audit event. Never raises on payload content; keep payloads small."""
    event = AuditEvent(
        institution_id=institution_id,
        actor_user_id=actor_user_id,
        event_type=event_type.value if isinstance(event_type, AuditAction) else str(event_type),
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload or {},
    )
    session.add(event)
    if flush:
        await session.flush()
    return event


async def record_scoped_read(
    session: AsyncSession,
    *,
    principal: object,
    scope: object,
    resource: str,
    rows_returned: int,
    detail: str | None = None,
) -> AuditEvent:
    """Record a governed read, including how many rows the caller's scope allowed through.

    `rows_returned == 0` on a scoped read is the signal worth keeping: it is what proves a
    request for out-of-scope data came back empty rather than being refused with a message
    that would itself confirm the data exists.
    """
    payload: dict[str, Any] = {
        "resource": resource,
        "rows_returned": rows_returned,
        "unrestricted": bool(getattr(scope, "unrestricted", False)),
        "scoped_students": len(getattr(scope, "student_ids", ()) or ()),
    }
    if detail:
        payload["detail"] = detail
    return await record_event(
        session,
        institution_id=principal.institution_id,  # type: ignore[attr-defined]
        actor_user_id=principal.user_id,  # type: ignore[attr-defined]
        event_type=AuditAction.SCOPED_READ,
        entity_type=resource,
        payload=payload,
    )


async def list_events(
    session: AsyncSession,
    *,
    institution_id: UUID,
    limit: int = 100,
    event_type: str | None = None,
) -> list[AuditEvent]:
    """Newest first. Institution-scoped: an administrator never sees another tenant."""
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.institution_id == institution_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(min(limit, 500))
    )
    if event_type:
        stmt = stmt.where(AuditEvent.event_type == event_type)
    return list(await session.scalars(stmt))

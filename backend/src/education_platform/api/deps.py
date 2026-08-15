"""Authentication dependencies."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.db.session import get_session
from education_platform.modules.audit.service import AuditAction, record_event
from education_platform.modules.auth.models import StudentProfile, User, UserRole, UserStatus
from education_platform.modules.auth.security import decode_token
from education_platform.modules.authorization.scope import Scope, scope_for

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: UUID
    institution_id: UUID
    email: str
    roles: frozenset[str]
    student_profile_id: UUID | None
    status: str

    @property
    def is_administrator(self) -> bool:
        return "administrator" in self.roles

    @property
    def is_student(self) -> bool:
        return "student" in self.roles


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_token(credentials.credentials)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token"
        ) from exc
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token")

    user = await session.get(User, UUID(str(user_id)))
    if user is None or user.status not in {UserStatus.ACTIVE, UserStatus.PROVISIONED}:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    roles = (await session.scalars(select(UserRole.role).where(UserRole.user_id == user.id))).all()
    profile_id = await session.scalar(
        select(StudentProfile.id).where(StudentProfile.user_id == user.id)
    )
    return Principal(
        user_id=user.id,
        institution_id=user.institution_id,
        email=user.email,
        roles=frozenset(role.value for role in roles),
        student_profile_id=profile_id,
        status=user.status.value,
    )


async def require_administrator(
    principal: Principal = Depends(get_current_user),
) -> Principal:
    if not principal.is_administrator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator role required",
        )
    return principal


def require_role(*roles: str) -> Callable[..., Awaitable[Principal]]:
    """Gate a route on holding at least one of `roles`.

    Use this instead of hand-writing a 403 in a service function, so that every role check
    in the codebase is the same check and can be tested once.
    """
    allowed = frozenset(roles)

    async def _dependency(
        principal: Principal = Depends(get_current_user),
    ) -> Principal:
        if not (principal.roles & allowed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {', '.join(sorted(allowed))}",
            )
        return principal

    return _dependency


async def get_scope(
    principal: Principal = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Scope:
    """Resolve the caller's data boundary once, before any handler reads anything."""
    return await scope_for(session, principal)


@dataclass(frozen=True, slots=True)
class ScopedRequest:
    """A principal plus their resolved boundary, for handlers that read student data."""

    principal: Principal
    scope: Scope
    session: AsyncSession


def scoped(resource: str) -> Callable[..., Awaitable[ScopedRequest]]:
    """Dependency for any route that reads student data.

    Resolves the caller's scope and records the access in the audit trail. `resource` names
    what was read and appears in the audit screen. Handlers should call
    `audit.record_scoped_read` afterwards if they want the row count recorded too.
    """

    async def _dependency(
        principal: Principal = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> ScopedRequest:
        scope = await scope_for(session, principal)
        await record_event(
            session,
            institution_id=principal.institution_id,
            actor_user_id=principal.user_id,
            event_type=AuditAction.SCOPED_READ,
            entity_type=resource,
            payload={
                "resource": resource,
                "unrestricted": scope.unrestricted,
                "scoped_students": len(scope.student_ids),
            },
        )
        return ScopedRequest(principal=principal, scope=scope, session=session)

    return _dependency

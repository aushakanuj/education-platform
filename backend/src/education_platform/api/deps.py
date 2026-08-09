"""Authentication dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.db.session import get_session
from education_platform.modules.auth.models import StudentProfile, User, UserRole, UserStatus
from education_platform.modules.auth.security import decode_token

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

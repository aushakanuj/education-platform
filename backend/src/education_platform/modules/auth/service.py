"""Auth business logic."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.modules.auth.models import (
    Institution,
    RefreshSession,
    RoleName,
    StudentProfile,
    StudentProfileStatus,
    User,
    UserRole,
    UserStatus,
)
from education_platform.modules.auth.schemas import (
    LoginRequest,
    MeResponse,
    ProvisionStudentRequest,
    TokenResponse,
)
from education_platform.modules.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


async def _roles_for_user(session: AsyncSession, user_id: UUID) -> list[str]:
    roles = (await session.scalars(select(UserRole.role).where(UserRole.user_id == user_id))).all()
    return sorted(role.value for role in roles)


async def _student_profile_id(session: AsyncSession, user_id: UUID) -> UUID | None:
    profile_id = await session.scalar(
        select(StudentProfile.id).where(StudentProfile.user_id == user_id)
    )
    return profile_id if isinstance(profile_id, UUID) else None


async def login(session: AsyncSession, payload: LoginRequest) -> TokenResponse:
    stmt = select(User).where(User.email == str(payload.email).lower())
    if payload.institution_name:
        institution = await session.scalar(
            select(Institution).where(Institution.name == payload.institution_name)
        )
        if institution is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
            )
        stmt = stmt.where(User.institution_id == institution.id)

    users = (await session.scalars(stmt)).all()
    if len(users) != 1:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    user = users[0]
    if user.status not in {UserStatus.ACTIVE, UserStatus.PROVISIONED}:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not verify_password(user.password_hash, payload.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if user.status == UserStatus.PROVISIONED:
        user.status = UserStatus.ACTIVE

    access = create_access_token(user_id=user.id, institution_id=user.institution_id)
    refresh, token_hash, expires_at = create_refresh_token(user_id=user.id)
    session.add(
        RefreshSession(
            user_id=user.id, token_hash=token_hash, expires_at=expires_at, revoked_at=None
        )
    )
    await session.commit()
    return TokenResponse(access_token=access, refresh_token=refresh)


async def refresh(session: AsyncSession, refresh_token: str) -> TokenResponse:
    try:
        payload = decode_token(refresh_token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        ) from exc
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    token_hash = payload.get("jti")
    user_id = payload.get("sub")
    if not token_hash or not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    stored = await session.scalar(
        select(RefreshSession).where(RefreshSession.token_hash == token_hash)
    )
    if stored is None or stored.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    expires_at = stored.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    user = await session.get(User, UUID(str(user_id)))
    if user is None or user.status not in {UserStatus.ACTIVE, UserStatus.PROVISIONED}:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    stored.revoked_at = datetime.now(UTC)
    access = create_access_token(user_id=user.id, institution_id=user.institution_id)
    new_refresh, new_hash, expires_at = create_refresh_token(user_id=user.id)
    session.add(
        RefreshSession(user_id=user.id, token_hash=new_hash, expires_at=expires_at, revoked_at=None)
    )
    await session.commit()
    return TokenResponse(access_token=access, refresh_token=new_refresh)


async def logout(session: AsyncSession, refresh_token: str) -> None:
    try:
        payload = decode_token(refresh_token)
    except Exception:
        return
    token_hash = payload.get("jti")
    if not token_hash:
        return
    stored = await session.scalar(
        select(RefreshSession).where(RefreshSession.token_hash == token_hash)
    )
    if stored is not None and stored.revoked_at is None:
        stored.revoked_at = datetime.now(UTC)
        await session.commit()


async def me(session: AsyncSession, user_id: UUID) -> MeResponse:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    return MeResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        institution_id=user.institution_id,
        roles=await _roles_for_user(session, user.id),
        student_profile_id=await _student_profile_id(session, user.id),
        status=user.status.value,
    )


async def provision_student(session: AsyncSession, payload: ProvisionStudentRequest) -> MeResponse:
    """POC helper: create/link a student account in an existing institution."""
    institution = await session.scalar(
        select(Institution).where(Institution.name == payload.institution_name)
    )
    if institution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Institution '{payload.institution_name}' not found; seed materials first",
        )

    email = str(payload.email).lower()
    existing = await session.scalar(
        select(User).where(User.institution_id == institution.id, User.email == email)
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")

    user = User(
        institution_id=institution.id,
        email=email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        status=UserStatus.ACTIVE,
    )
    session.add(user)
    await session.flush()
    session.add(UserRole(user_id=user.id, role=RoleName.STUDENT))

    profile = await session.scalar(
        select(StudentProfile).where(
            StudentProfile.institution_id == institution.id,
            StudentProfile.student_identifier == payload.student_identifier,
        )
    )
    if profile is None:
        profile = StudentProfile(
            institution_id=institution.id,
            user_id=user.id,
            student_identifier=payload.student_identifier,
            full_name=payload.full_name,
            status=StudentProfileStatus.ACTIVE,
        )
        session.add(profile)
    else:
        if profile.user_id is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Student identifier already linked to a user",
            )
        profile.user_id = user.id
        profile.full_name = payload.full_name

    await session.commit()
    return await me(session, user.id)

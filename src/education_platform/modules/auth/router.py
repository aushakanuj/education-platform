from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from education_platform.api.deps import AdminUser, SessionDep
from education_platform.core.config import get_settings
from education_platform.modules.auth.models import Institution, RefreshSession, User, UserRole
from education_platform.modules.auth.schemas import (
    LoginRequest,
    RefreshRequest,
    TokenPair,
    UserCreate,
    UserRead,
)
from education_platform.modules.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    token_hash,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


async def issue_tokens(session: SessionDep, user: User) -> TokenPair:
    access_token = create_access_token(user.id, user.role.value)
    refresh_token, expires_at = create_refresh_token(user.id)
    session.add(
        RefreshSession(user_id=user.id, token_hash=token_hash(refresh_token), expires_at=expires_at)
    )
    await session.commit()
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/bootstrap-admin", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def bootstrap_admin(payload: UserCreate, session: SessionDep) -> UserRead:
    if get_settings().environment != "development":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    user_count = await session.scalar(select(func.count()).select_from(User))
    if user_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Platform already initialized"
        )
    institution = Institution(name="Development Institution")
    session.add(institution)
    await session.flush()
    admin = User(
        institution_id=institution.id,
        email=str(payload.email).lower(),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=UserRole.ADMIN,
    )
    session.add(admin)
    await session.commit()
    await session.refresh(admin)
    return UserRead(
        id=admin.id, email=admin.email, full_name=admin.full_name, role=admin.role.value
    )


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginRequest, session: SessionDep) -> TokenPair:
    user = await session.scalar(select(User).where(User.email == str(payload.email).lower()))
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    return await issue_tokens(session, user)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, session: SessionDep) -> TokenPair:
    try:
        token_payload = decode_token(payload.refresh_token, expected_type="refresh")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        ) from exc
    existing_session = await session.scalar(
        select(RefreshSession).where(
            RefreshSession.token_hash == token_hash(payload.refresh_token),
            RefreshSession.revoked_at.is_(None),
        )
    )
    if existing_session is None or existing_session.expires_at < datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired"
        )
    user = await session.get(User, token_payload["sub"])
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    existing_session.revoked_at = datetime.now(UTC)
    return await issue_tokens(session, user)


@router.post("/teachers", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_teacher(payload: UserCreate, admin: AdminUser, session: SessionDep) -> UserRead:
    existing = await session.scalar(select(User).where(User.email == str(payload.email).lower()))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    teacher = User(
        institution_id=admin.institution_id,
        email=str(payload.email).lower(),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=UserRole.TEACHER,
    )
    session.add(teacher)
    await session.commit()
    await session.refresh(teacher)
    return UserRead(
        id=teacher.id, email=teacher.email, full_name=teacher.full_name, role=teacher.role.value
    )

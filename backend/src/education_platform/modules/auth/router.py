"""Auth HTTP routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.api.deps import Principal, get_current_user
from education_platform.db.session import get_session
from education_platform.modules.auth import service
from education_platform.modules.auth.schemas import (
    LoginRequest,
    MeResponse,
    ProvisionStudentRequest,
    RefreshRequest,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    return await service.login(session, payload)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    return await service.refresh(session, payload.refresh_token)


@router.post("/logout", status_code=204)
async def logout(payload: RefreshRequest, session: AsyncSession = Depends(get_session)) -> None:
    await service.logout(session, payload.refresh_token)


@router.get("/me", response_model=MeResponse)
async def read_me(
    principal: Principal = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MeResponse:
    return await service.me(session, principal.user_id)


@router.post("/provision-student", response_model=MeResponse)
async def provision_student(
    payload: ProvisionStudentRequest, session: AsyncSession = Depends(get_session)
) -> MeResponse:
    """POC-only account provisioning until admin roster APIs exist."""
    return await service.provision_student(session, payload)

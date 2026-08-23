"""Academic / enrollment routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.api.deps import Principal, get_current_user, get_scope
from education_platform.core.config import Settings, get_settings
from education_platform.db.session import get_session
from education_platform.modules.academics import demo, service
from education_platform.modules.academics.schemas import (
    DemoBootstrapOut,
    DemoResetOut,
    EnrollmentSummary,
    EnrollMeRequest,
)
from education_platform.modules.authorization.scope import Scope, scope_for
from education_platform.modules.materials.schemas import LearningDirectoryOut
from education_platform.modules.materials.service import build_learning_directory

router = APIRouter(tags=["enrollments"])


def _require_dev(settings: Settings) -> None:
    if not settings.is_development:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Development-only helper disabled",
        )


@router.get("/me/enrollments", response_model=EnrollmentSummary)
async def my_enrollments(
    scope: Scope = Depends(get_scope),
    session: AsyncSession = Depends(get_session),
) -> EnrollmentSummary:
    return await service.list_my_enrollments(session, scope)


@router.post("/me/enrollments/poc-math", response_model=EnrollmentSummary)
async def enroll_me_poc_math(
    payload: EnrollMeRequest,
    principal: Principal = Depends(get_current_user),
    scope: Scope = Depends(get_scope),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> EnrollmentSummary:
    _require_dev(settings)
    if not payload.confirm:
        return await service.list_my_enrollments(session, scope)
    if principal.student_profile_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Student profile required"
        )
    await service.enroll_student_in_poc_math(
        session, student_profile_id=principal.student_profile_id
    )
    refreshed = await scope_for(session, principal)
    return await service.list_my_enrollments(session, refreshed)


@router.post("/me/demo/bootstrap", response_model=DemoBootstrapOut)
async def demo_bootstrap(
    principal: Principal = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> DemoBootstrapOut:
    _require_dev(settings)
    return await demo.bootstrap_demo(session, principal)


@router.post("/me/demo/reset", response_model=DemoResetOut)
async def demo_reset(
    principal: Principal = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> DemoResetOut:
    _require_dev(settings)
    return await demo.reset_demo(session, principal)


@router.get("/me/learning-directory", response_model=LearningDirectoryOut)
async def learning_directory(
    scope: Scope = Depends(get_scope),
    session: AsyncSession = Depends(get_session),
) -> LearningDirectoryOut:
    return await build_learning_directory(session, scope)

"""Academic / enrollment routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.api.deps import Principal, get_current_user
from education_platform.db.session import get_session
from education_platform.modules.academics import service
from education_platform.modules.academics.schemas import EnrollmentSummary, EnrollMeRequest

router = APIRouter(tags=["enrollments"])


@router.get("/me/enrollments", response_model=EnrollmentSummary)
async def my_enrollments(
    principal: Principal = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> EnrollmentSummary:
    return await service.list_my_enrollments(session, principal)


@router.post("/me/enrollments/poc-math", response_model=EnrollmentSummary)
async def enroll_me_poc_math(
    payload: EnrollMeRequest,
    principal: Principal = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> EnrollmentSummary:
    if not payload.confirm:
        return await service.list_my_enrollments(session, principal)
    if principal.student_profile_id is None:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Student profile required"
        )
    await service.enroll_student_in_poc_math(
        session, student_profile_id=principal.student_profile_id
    )
    return await service.list_my_enrollments(session, principal)

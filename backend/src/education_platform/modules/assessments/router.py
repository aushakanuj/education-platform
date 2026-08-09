"""Assessment / quiz attempt routes."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.api.deps import Principal, get_current_user
from education_platform.db.session import get_session
from education_platform.modules.assessments import service
from education_platform.modules.assessments.schemas import (
    AttemptResult,
    StartAttemptResponse,
    SubmitAttemptRequest,
)
from education_platform.modules.materials.schemas import AttemptHistoryItem

router = APIRouter(tags=["attempts"])


@router.post("/quizzes/{quiz_id}/attempts", response_model=StartAttemptResponse)
async def start_quiz_attempt(
    quiz_id: UUID,
    principal: Principal = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StartAttemptResponse:
    return await service.start_attempt(session, principal, quiz_id)


@router.get("/quizzes/{quiz_id}/attempts", response_model=list[AttemptHistoryItem])
async def list_quiz_attempts(
    quiz_id: UUID,
    principal: Principal = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[AttemptHistoryItem]:
    return await service.list_attempts_for_quiz(session, principal, quiz_id)


@router.post("/attempts/{attempt_id}/submit", response_model=AttemptResult)
async def submit_quiz_attempt(
    attempt_id: UUID,
    payload: SubmitAttemptRequest,
    principal: Principal = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AttemptResult:
    return await service.submit_attempt(session, principal, attempt_id, payload)


@router.get("/attempts/{attempt_id}", response_model=AttemptResult)
async def get_quiz_attempt(
    attempt_id: UUID,
    principal: Principal = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AttemptResult:
    return await service.get_attempt(session, principal, attempt_id)

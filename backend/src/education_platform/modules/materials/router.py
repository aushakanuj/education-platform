from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.api.deps import Principal, get_current_user
from education_platform.db.session import get_session
from education_platform.modules.materials import service
from education_platform.modules.materials.schemas import LessonMaterial, QuizMaterial, TopicSummary

router = APIRouter(prefix="/materials", tags=["materials"])


@router.get("", response_model=list[TopicSummary])
async def list_materials(
    principal: Principal = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[TopicSummary]:
    return await service.list_topics(session, principal)


@router.get("/{topic_id}", response_model=LessonMaterial)
async def get_material(
    topic_id: str,
    principal: Principal = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LessonMaterial:
    return await service.get_lesson(session, principal, topic_id)


@router.get("/{topic_id}/quiz", response_model=QuizMaterial)
async def get_material_quiz(
    topic_id: str,
    principal: Principal = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> QuizMaterial:
    return await service.get_quiz(session, principal, topic_id)

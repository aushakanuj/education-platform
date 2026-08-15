"""Admin policy chat routes (multi-conversation)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.api.deps import Principal, require_administrator
from education_platform.db.session import get_session
from education_platform.modules.assistant import service
from education_platform.modules.assistant.schemas import (
    ConversationDetailOut,
    ConversationSummaryOut,
    CreateConversationIn,
    CreateConversationOut,
    PostMessageIn,
    PostMessageOut,
)

router = APIRouter(tags=["assistant"])


@router.get("/chats", response_model=list[ConversationSummaryOut])
async def list_chats(
    principal: Principal = Depends(require_administrator),
    session: AsyncSession = Depends(get_session),
) -> list[ConversationSummaryOut]:
    return await service.list_conversations(session, principal)


@router.post(
    "/chats",
    response_model=CreateConversationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_chat(
    body: CreateConversationIn | None = None,
    principal: Principal = Depends(require_administrator),
    session: AsyncSession = Depends(get_session),
) -> CreateConversationOut:
    title = body.title if body else None
    return await service.create_conversation(session, principal, title=title)


@router.get("/chats/{conversation_id}", response_model=ConversationDetailOut)
async def get_chat(
    conversation_id: UUID,
    principal: Principal = Depends(require_administrator),
    session: AsyncSession = Depends(get_session),
) -> ConversationDetailOut:
    return await service.get_conversation(session, principal, conversation_id)


@router.delete("/chats/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
    conversation_id: UUID,
    principal: Principal = Depends(require_administrator),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await service.delete_conversation(session, principal, conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/chats/{conversation_id}/messages", response_model=PostMessageOut)
async def post_chat_message(
    conversation_id: UUID,
    body: PostMessageIn,
    principal: Principal = Depends(require_administrator),
    session: AsyncSession = Depends(get_session),
) -> PostMessageOut:
    return await service.post_message(
        session,
        principal,
        conversation_id,
        content=body.content,
    )

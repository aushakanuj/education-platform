"""POLICY assistant graph: existing LangGraph handbook retrieve. Admin `/chats` only."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.modules.assistant.graph import run_assistant_turn
from education_platform.modules.assistant.strategy import (
    AssistantContext,
    AssistantKind,
    AssistantReply,
    ChatCitation,
    ChatTurn,
)
from education_platform.modules.authorization.principal import Principal


class PolicyAssistantStrategy:
    kind = AssistantKind.POLICY

    async def run_turn(
        self,
        *,
        session: AsyncSession,
        principal: Principal,
        context: AssistantContext,
        history: tuple[ChatTurn, ...],
        message: str,
    ) -> AssistantReply:
        del session
        if context.kind != "policy":
            raise TypeError("policy graph requires a policy context")
        result = await run_assistant_turn(
            principal=principal,
            user_message=message,
            history=[{"role": turn.role, "content": turn.content} for turn in history],
        )
        citations: list[ChatCitation] = []
        for item in result.get("citations") or []:
            if not isinstance(item, dict):
                continue
            citation_id = str(item.get("id") or "")
            label = str(item.get("label") or "")
            excerpt = str(item.get("excerpt") or "")
            if citation_id and label and excerpt:
                citations.append(ChatCitation(id=citation_id, label=label, excerpt=excerpt))
        return AssistantReply(
            content=str(result.get("assistant_content") or ""),
            citations=tuple(citations),
            draft_change_request=None,
        )

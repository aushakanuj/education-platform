"""Assistant graph strategies: policy handbook vs generation-review drafts.

Implementations import types from this module. `graph_for` loads them lazily so
this file does not import the graphs (cycle).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.modules.authorization.principal import Principal
from education_platform.modules.generation.types import DraftChangeRequest, ReviewTarget


class AssistantKind(StrEnum):
    POLICY = "policy"
    GENERATION_REVIEW = "generation_review"


@dataclass(frozen=True, slots=True)
class ChatTurn:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class ChatCitation:
    id: str
    label: str
    excerpt: str


@dataclass(frozen=True, slots=True)
class PolicyAssistantContext:
    kind: Literal["policy"]
    institution_id: UUID


@dataclass(frozen=True, slots=True)
class GenerationAssistantContext:
    kind: Literal["generation_review"]
    run_id: UUID
    revision_id: UUID
    target: ReviewTarget | None


AssistantContext = PolicyAssistantContext | GenerationAssistantContext


@dataclass(frozen=True, slots=True)
class AssistantReply:
    content: str
    citations: tuple[ChatCitation, ...]
    draft_change_request: DraftChangeRequest | None


class AssistantGraph(Protocol):
    kind: AssistantKind

    async def run_turn(
        self,
        *,
        session: AsyncSession,
        principal: Principal,
        context: AssistantContext,
        history: tuple[ChatTurn, ...],
        message: str,
    ) -> AssistantReply:
        """Authorize context and produce a reply. Must not submit review decisions."""


def graph_for(kind: AssistantKind) -> AssistantGraph:
    """Return the graph for `kind`. Lazy imports keep POLICY and GENERATION_REVIEW isolated."""
    if kind is AssistantKind.POLICY:
        from education_platform.modules.assistant.policy_strategy import PolicyAssistantStrategy

        return PolicyAssistantStrategy()
    if kind is AssistantKind.GENERATION_REVIEW:
        from education_platform.modules.assistant.generation_strategy import (
            GenerationReviewStrategy,
        )

        return GenerationReviewStrategy()
    raise ValueError(f"unsupported assistant kind: {kind}")

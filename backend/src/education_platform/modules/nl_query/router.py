"""Ask the data in English. One endpoint, bounded by the caller's scope."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from education_platform.api.deps import ScopedRequest, scoped
from education_platform.modules.insights.service import MAX_ROWS
from education_platform.modules.nl_query import service

router = APIRouter(tags=["ask"])


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=100, ge=1, le=MAX_ROWS)


class AskOut(BaseModel):
    question: str
    answered: bool
    #: Present when `answered` is false — says what is missing, in plain words.
    reason: str | None = None
    #: The query the model wrote. Shown so the number can be checked.
    model_sql: str | None = None
    #: What actually ran, with the permission boundary prepended. Shown so the
    #: boundary is visible rather than merely promised.
    executed_sql: str | None = None
    columns: list[str] = []
    rows: list[list[Any]] = []
    row_count: int = 0
    truncated: bool = False


@router.post("/ask/students", response_model=AskOut)
async def ask_students(
    payload: AskIn,
    request: ScopedRequest = Depends(scoped("nl_query.students")),
) -> AskOut:
    """Answer a question about students, within what the caller may see.

    The model never learns who is asking. The boundary is applied to the query after it is
    written, so a question about a class the caller does not teach returns zero rows rather
    than an error — an error would confirm the class exists.
    """
    answer = await service.answer_question(payload.question, request.scope, row_limit=payload.limit)

    await request.record_rows(
        answer.row_count,
        detail=f"question={answer.question!r}"
        + ("" if answer.answered else f" unanswered={answer.reason!r}"),
    )
    await request.session.commit()

    # asdict, not vars: QueryAnswer uses slots and so has no __dict__. The same mistake
    # took down /insights/students in Stage 1, which is why this route has API-level tests.
    return AskOut(**asdict(answer))

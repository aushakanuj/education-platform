"""Teacher authoring: generate draft questions, review them, publish or discard."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from education_platform.api.deps import ScopedRequest, scoped
from education_platform.modules.assessments.models import QuestionDifficulty
from education_platform.modules.authoring import service
from education_platform.modules.authoring.service import AuthoringError

router = APIRouter(tags=["authoring"])


def _refuse(exc: AuthoringError) -> HTTPException:
    """Authoring is an action, so a refusal is a 403 rather than an empty result.

    This is the `capability is refused, content is empty` rule from docs/design/02: a
    teacher cannot *author* outside what they teach, and saying so leaks nothing they
    could not already work out from their own timetable.
    """
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


class SubtopicOut(BaseModel):
    id: UUID
    name: str
    subject: str
    topic: str
    draft_count: int


class GenerateIn(BaseModel):
    count: int = Field(default=5, ge=1, le=service.MAX_PER_REQUEST)
    difficulty: QuestionDifficulty = QuestionDifficulty.MEDIUM


class OptionOut(BaseModel):
    label: str
    text: str


class DraftOut(BaseModel):
    id: UUID
    prompt: str
    options: list[OptionOut]
    correct_label: str | None
    explanation: str | None
    difficulty: str | None


class GenerateOut(BaseModel):
    subtopic_id: UUID
    subtopic_name: str
    created: int
    #: Questions the model produced that failed validation, and why. Shown rather than
    #: hidden so a teacher can see the tool is being checked.
    rejected: list[str]
    drafts: list[DraftOut]


@router.get("/authoring/subtopics", response_model=list[SubtopicOut])
async def list_subtopics(
    request: ScopedRequest = Depends(scoped("authoring.subtopics")),
) -> list[SubtopicOut]:
    """Subtopics the caller may write questions for — those they teach."""
    rows = await service.authorable_subtopics(request.session, request.scope)
    await request.record_rows(len(rows))
    await request.session.commit()
    return [
        SubtopicOut(id=s.id, name=s.name, subject=subject, topic=topic, draft_count=drafts)
        for s, subject, topic, drafts in rows
    ]


async def _drafts_payload(request: ScopedRequest, subtopic_id: UUID) -> list[DraftOut]:
    drafts = await service.list_drafts(request.session, request.scope, subtopic_id)
    return [
        DraftOut(
            id=version.id,
            prompt=version.prompt,
            options=[OptionOut(label=o.label, text=o.text) for o in options],
            correct_label=key,
            explanation=version.explanation,
            difficulty=version.difficulty.value if version.difficulty else None,
        )
        for version, options, key in drafts
    ]


@router.get("/authoring/subtopics/{subtopic_id}/drafts", response_model=list[DraftOut])
async def list_drafts(
    subtopic_id: UUID,
    request: ScopedRequest = Depends(scoped("authoring.drafts")),
) -> list[DraftOut]:
    try:
        payload = await _drafts_payload(request, subtopic_id)
    except AuthoringError as exc:
        raise _refuse(exc) from exc
    await request.record_rows(len(payload))
    await request.session.commit()
    return payload


@router.post("/authoring/subtopics/{subtopic_id}/generate", response_model=GenerateOut)
async def generate(
    subtopic_id: UUID,
    payload: GenerateIn,
    request: ScopedRequest = Depends(scoped("authoring.generate")),
) -> GenerateOut:
    """Generate draft questions. Nothing generated here is visible to a student."""
    try:
        result = await service.generate_questions(
            request.session,
            request.scope,
            subtopic_id,
            count=payload.count,
            difficulty=payload.difficulty,
        )
        drafts = await _drafts_payload(request, subtopic_id)
    except AuthoringError as exc:
        raise _refuse(exc) from exc

    await request.record_rows(
        len(result.created),
        detail=f"generated={len(result.created)} rejected={len(result.rejected)}",
    )
    await request.session.commit()

    return GenerateOut(
        subtopic_id=subtopic_id,
        subtopic_name=result.subtopic_name,
        created=len(result.created),
        rejected=result.rejected,
        drafts=drafts,
    )


@router.post("/authoring/drafts/{version_id}/publish", status_code=status.HTTP_204_NO_CONTENT)
async def publish(
    version_id: UUID,
    request: ScopedRequest = Depends(scoped("authoring.publish")),
) -> None:
    try:
        await service.publish_draft(request.session, request.scope, version_id)
    except AuthoringError as exc:
        raise _refuse(exc) from exc
    await request.record_rows(1, detail=f"published={version_id}")
    await request.session.commit()


@router.delete("/authoring/drafts/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
async def discard(
    version_id: UUID,
    request: ScopedRequest = Depends(scoped("authoring.discard")),
) -> None:
    try:
        await service.discard_draft(request.session, request.scope, version_id)
    except AuthoringError as exc:
        raise _refuse(exc) from exc
    await request.record_rows(1, detail=f"discarded={version_id}")
    await request.session.commit()

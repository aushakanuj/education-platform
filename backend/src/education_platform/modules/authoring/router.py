"""Teacher authoring: generate draft questions, review them, publish or discard."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from education_platform.api.deps import ScopedRequest, scoped
from education_platform.modules.assessments.models import (
    QuestionDifficulty,
    QuestionVersionStatus,
)
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
    #: Approved questions already in the bank, so a teacher can see where the ones they
    #: approved went. Without it, approving a draft just makes the count go down.
    published_count: int


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
        SubtopicOut(
            id=s.id,
            name=s.name,
            subject=subject,
            topic=topic,
            draft_count=drafts,
            published_count=published,
        )
        for s, subject, topic, drafts, published in rows
    ]


async def _questions_payload(
    request: ScopedRequest, subtopic_id: UUID, status_filter: QuestionVersionStatus
) -> list[DraftOut]:
    rows = await service.list_questions(request.session, request.scope, subtopic_id, status_filter)
    return [
        DraftOut(
            id=version.id,
            prompt=version.prompt,
            options=[OptionOut(label=o.label, text=o.text) for o in options],
            correct_label=key,
            explanation=version.explanation,
            difficulty=version.difficulty.value if version.difficulty else None,
        )
        for version, options, key in rows
    ]


@router.get("/authoring/subtopics/{subtopic_id}/drafts", response_model=list[DraftOut])
async def list_drafts(
    subtopic_id: UUID,
    request: ScopedRequest = Depends(scoped("authoring.drafts")),
) -> list[DraftOut]:
    try:
        payload = await _questions_payload(request, subtopic_id, QuestionVersionStatus.DRAFT)
    except AuthoringError as exc:
        raise _refuse(exc) from exc
    await request.record_rows(len(payload))
    await request.session.commit()
    return payload


@router.get("/authoring/subtopics/{subtopic_id}/questions", response_model=list[DraftOut])
async def list_approved(
    subtopic_id: UUID,
    request: ScopedRequest = Depends(scoped("authoring.questions")),
) -> list[DraftOut]:
    """The approved bank for a subtopic: what a teacher has already said yes to.

    Same authorisation as the drafts list, and for a stronger reason -- these carry answer
    keys, so this stays a teaching path and never becomes a student-reachable one.
    """
    try:
        payload = await _questions_payload(request, subtopic_id, QuestionVersionStatus.PUBLISHED)
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
        drafts = await _questions_payload(request, subtopic_id, QuestionVersionStatus.DRAFT)
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

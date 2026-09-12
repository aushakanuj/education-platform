"""Teacher authoring: generate draft questions, review, publish or discard."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status

from education_platform.api.deps import ScopedRequest, scoped
from education_platform.modules.assessments.models import QuestionVersionStatus
from education_platform.modules.authoring import service
from education_platform.modules.authoring.schemas import (
    DraftOut,
    GenerateIn,
    GenerateOut,
    OptionOut,
    SubtopicOut,
)

router = APIRouter(tags=["authoring"])


@router.get("/authoring/subtopics", response_model=list[SubtopicOut])
async def list_subtopics(
    request: ScopedRequest = Depends(scoped("authoring.subtopics")),
) -> list[SubtopicOut]:
    rows = await service.authorable_subtopics(request.session, request.scope)
    await request.record_rows(len(rows))
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
    payload = await _questions_payload(request, subtopic_id, QuestionVersionStatus.DRAFT)
    await request.record_rows(len(payload))
    return payload


@router.get("/authoring/subtopics/{subtopic_id}/questions", response_model=list[DraftOut])
async def list_approved(
    subtopic_id: UUID,
    request: ScopedRequest = Depends(scoped("authoring.questions")),
) -> list[DraftOut]:
    payload = await _questions_payload(request, subtopic_id, QuestionVersionStatus.PUBLISHED)
    await request.record_rows(len(payload))
    return payload


@router.post("/authoring/subtopics/{subtopic_id}/generate", response_model=GenerateOut)
async def generate(
    subtopic_id: UUID,
    payload: GenerateIn,
    request: ScopedRequest = Depends(scoped("authoring.generate")),
) -> GenerateOut:
    result = await service.generate_questions(
        request.session,
        request.scope,
        subtopic_id,
        count=payload.count,
        difficulty=payload.difficulty,
    )
    drafts = await _questions_payload(request, subtopic_id, QuestionVersionStatus.DRAFT)
    await request.record_rows(
        len(result.created),
        detail=f"generated={len(result.created)} rejected={len(result.rejected)}",
    )
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
    await service.publish_draft(request.session, request.scope, version_id)
    await request.record_rows(1, detail=f"published={version_id}")


@router.delete("/authoring/drafts/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
async def discard(
    version_id: UUID,
    request: ScopedRequest = Depends(scoped("authoring.discard")),
) -> None:
    await service.discard_draft(request.session, request.scope, version_id)
    await request.record_rows(1, detail=f"discarded={version_id}")

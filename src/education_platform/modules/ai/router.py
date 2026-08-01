from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from education_platform.api.deps import SessionDep, TeacherUser
from education_platform.modules.ai.models import Conversation, ConversationMessage, MessageCitation
from education_platform.modules.ai.schemas import (
    AnswerRead,
    AskRequest,
    CitationRead,
    LessonGenerateRequest,
    LessonPlanRead,
)
from education_platform.modules.curriculum.models import (
    CurriculumCollection,
    CurriculumDocument,
    DocumentChunk,
    DocumentStatus,
    TeacherCollectionAssignment,
)

router = APIRouter(prefix="/assistant", tags=["teacher assistant"])


async def get_authorized_chunks(
    session: SessionDep, teacher: TeacherUser, collection_id: object
) -> list[tuple[DocumentChunk, CurriculumDocument]]:
    assigned = await session.scalar(
        select(TeacherCollectionAssignment).where(
            TeacherCollectionAssignment.teacher_id == teacher.id,
            TeacherCollectionAssignment.collection_id == collection_id,
        )
    )
    if assigned is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Collection is not assigned"
        )
    result = await session.execute(
        select(DocumentChunk, CurriculumDocument)
        .join(CurriculumDocument, CurriculumDocument.id == DocumentChunk.document_id)
        .join(CurriculumCollection, CurriculumCollection.id == CurriculumDocument.collection_id)
        .where(
            CurriculumDocument.collection_id == collection_id,
            CurriculumDocument.status == DocumentStatus.PUBLISHED,
            CurriculumCollection.institution_id == teacher.institution_id,
        )
        .limit(12)
    )
    return list(result.tuples())


def citations_from(chunks: list[tuple[DocumentChunk, CurriculumDocument]]) -> list[CitationRead]:
    return [
        CitationRead(
            document_id=document.id,
            filename=document.filename,
            locator=chunk.source_locator,
            excerpt=chunk.content[:300],
        )
        for chunk, document in chunks[:4]
    ]


@router.post("/ask", response_model=AnswerRead)
async def ask_question(
    payload: AskRequest, teacher: TeacherUser, session: SessionDep
) -> AnswerRead:
    chunks = await get_authorized_chunks(session, teacher, payload.collection_id)
    if not chunks:
        return AnswerRead(
            answer="I do not have enough approved curriculum evidence to answer this question.",
            citations=[],
        )
    question_terms = {term.lower() for term in payload.question.split() if len(term) > 3}
    ranked = sorted(
        chunks,
        key=lambda item: sum(term in item[0].content.lower() for term in question_terms),
        reverse=True,
    )
    evidence = ranked[:3]
    answer = "Based on the approved curriculum: " + " ".join(
        chunk.content[:500] for chunk, _ in evidence
    )
    conversation = Conversation(teacher_id=teacher.id, collection_id=payload.collection_id)
    session.add(conversation)
    await session.flush()
    session.add(
        ConversationMessage(conversation_id=conversation.id, role="user", content=payload.question)
    )
    assistant_message = ConversationMessage(
        conversation_id=conversation.id, role="assistant", content=answer
    )
    session.add(assistant_message)
    await session.flush()
    session.add_all(
        [
            MessageCitation(
                message_id=assistant_message.id, document_id=document.id, chunk_id=chunk.id
            )
            for chunk, document in evidence
        ]
    )
    await session.commit()
    return AnswerRead(answer=answer, citations=citations_from(evidence))


@router.post("/lesson-plans", response_model=LessonPlanRead)
async def generate_lesson_plan(
    payload: LessonGenerateRequest, teacher: TeacherUser, session: SessionDep
) -> LessonPlanRead:
    chunks = await get_authorized_chunks(session, teacher, payload.collection_id)
    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No published curriculum source is available for this collection",
        )
    citations = citations_from(chunks)
    return LessonPlanRead(
        title=f"{payload.topic}: {payload.duration_minutes}-minute lesson",
        learning_objectives=[
            f"Explain core ideas about {payload.topic}",
            f"Apply {payload.topic} using approved curriculum evidence",
        ],
        activities=[
            f"Opening discussion (10 minutes): introduce {payload.topic}",
            "Guided source reading (15 minutes): examine the cited curriculum sections",
            "Practice and reflection: apply the source concepts and summarize learning",
        ],
        source_citations=citations,
    )

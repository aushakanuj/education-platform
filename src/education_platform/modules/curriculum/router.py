from hashlib import sha256
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status
from sqlalchemy import select

from education_platform.api.deps import AdminUser, SessionDep, TeacherUser
from education_platform.core.config import get_settings
from education_platform.modules.auth.models import User, UserRole
from education_platform.modules.curriculum.ingestion import process_document
from education_platform.modules.curriculum.models import (
    CurriculumCollection,
    CurriculumDocument,
    DocumentStatus,
    TeacherCollectionAssignment,
)
from education_platform.modules.curriculum.schemas import (
    AssignmentCreate,
    CollectionCreate,
    CollectionRead,
    DocumentRead,
)
from education_platform.modules.curriculum.storage import storage

router = APIRouter(prefix="/curriculum", tags=["curriculum"])
ALLOWED_CONTENT_TYPES = {
    "text/plain",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def collection_read(collection: CurriculumCollection) -> CollectionRead:
    return CollectionRead(
        id=collection.id, title=collection.title, description=collection.description
    )


def document_read(document: CurriculumDocument) -> DocumentRead:
    return DocumentRead(
        id=document.id,
        filename=document.filename,
        status=document.status.value,
        version=document.version,
        failure_reason=document.failure_reason,
    )


async def get_admin_collection(
    session: SessionDep, admin: AdminUser, collection_id: UUID
) -> CurriculumCollection:
    collection = await session.scalar(
        select(CurriculumCollection).where(
            CurriculumCollection.id == collection_id,
            CurriculumCollection.institution_id == admin.institution_id,
        )
    )
    if collection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    return collection


@router.post("/collections", response_model=CollectionRead, status_code=status.HTTP_201_CREATED)
async def create_collection(
    payload: CollectionCreate, admin: AdminUser, session: SessionDep
) -> CollectionRead:
    collection = CurriculumCollection(
        institution_id=admin.institution_id, title=payload.title, description=payload.description
    )
    session.add(collection)
    await session.commit()
    await session.refresh(collection)
    return collection_read(collection)


@router.get("/collections", response_model=list[CollectionRead])
async def list_assigned_collections(
    teacher: TeacherUser, session: SessionDep
) -> list[CollectionRead]:
    result = await session.scalars(
        select(CurriculumCollection)
        .join(
            TeacherCollectionAssignment,
            TeacherCollectionAssignment.collection_id == CurriculumCollection.id,
        )
        .where(TeacherCollectionAssignment.teacher_id == teacher.id)
        .order_by(CurriculumCollection.title)
    )
    return [collection_read(collection) for collection in result]


@router.post("/collections/{collection_id}/teachers", status_code=status.HTTP_204_NO_CONTENT)
async def assign_teacher(
    collection_id: UUID, payload: AssignmentCreate, admin: AdminUser, session: SessionDep
) -> None:
    await get_admin_collection(session, admin, collection_id)
    teacher = await session.scalar(
        select(User).where(
            User.id == payload.teacher_id,
            User.institution_id == admin.institution_id,
            User.role == UserRole.TEACHER,
        )
    )
    if teacher is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found")
    existing = await session.scalar(
        select(TeacherCollectionAssignment).where(
            TeacherCollectionAssignment.teacher_id == teacher.id,
            TeacherCollectionAssignment.collection_id == collection_id,
        )
    )
    if existing is None:
        session.add(TeacherCollectionAssignment(teacher_id=teacher.id, collection_id=collection_id))
        await session.commit()


@router.post(
    "/collections/{collection_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    collection_id: UUID,
    background_tasks: BackgroundTasks,
    admin: AdminUser,
    session: SessionDep,
    file: UploadFile = File(...),
) -> DocumentRead:
    await get_admin_collection(session, admin, collection_id)
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported file type"
        )
    content = await file.read()
    if not content or len(content) > get_settings().max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Invalid file size"
        )
    filename = file.filename or "uploaded-file"
    object_key = f"{admin.institution_id}/{collection_id}/{uuid4()}-{filename}"
    await storage.save(object_key, content)
    document = CurriculumDocument(
        collection_id=collection_id,
        uploaded_by_id=admin.id,
        filename=filename,
        content_type=file.content_type,
        object_key=object_key,
        checksum=sha256(content).hexdigest(),
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)
    background_tasks.add_task(process_document, str(document.id))
    return document_read(document)


@router.get("/documents/{document_id}", response_model=DocumentRead)
async def get_document(document_id: UUID, admin: AdminUser, session: SessionDep) -> DocumentRead:
    document = await session.scalar(
        select(CurriculumDocument)
        .join(CurriculumCollection, CurriculumCollection.id == CurriculumDocument.collection_id)
        .where(
            CurriculumDocument.id == document_id,
            CurriculumCollection.institution_id == admin.institution_id,
        )
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document_read(document)


@router.post("/documents/{document_id}/publish", response_model=DocumentRead)
async def publish_document(
    document_id: UUID, admin: AdminUser, session: SessionDep
) -> DocumentRead:
    document = await session.scalar(
        select(CurriculumDocument)
        .join(CurriculumCollection, CurriculumCollection.id == CurriculumDocument.collection_id)
        .where(
            CurriculumDocument.id == document_id,
            CurriculumCollection.institution_id == admin.institution_id,
        )
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if document.status != DocumentStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Document is not ready to publish"
        )
    document.status = DocumentStatus.PUBLISHED
    await session.commit()
    await session.refresh(document)
    return document_read(document)

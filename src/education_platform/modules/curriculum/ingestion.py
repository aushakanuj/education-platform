from io import BytesIO

from docx import Document
from pypdf import PdfReader
from sqlalchemy import delete

from education_platform.db.session import SessionLocal
from education_platform.modules.curriculum.models import (
    CurriculumDocument,
    DocumentChunk,
    DocumentStatus,
)
from education_platform.modules.curriculum.storage import storage


def extract_text(content: bytes, content_type: str) -> list[tuple[str, str]]:
    if content_type == "text/plain":
        return [(content.decode("utf-8", errors="replace"), "text")]
    if content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        document = Document(BytesIO(content))
        return [("\n".join(paragraph.text for paragraph in document.paragraphs), "document")]
    if content_type == "application/pdf":
        reader = PdfReader(BytesIO(content))
        return [
            (page.extract_text() or "", f"page {index + 1}")
            for index, page in enumerate(reader.pages)
        ]
    raise ValueError("Unsupported file type")


def chunk_text(text: str, chunk_size: int = 1_200, overlap: int = 200) -> list[str]:
    normalized = " ".join(text.split())
    if not normalized:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + chunk_size)
        chunks.append(normalized[start:end])
        start += chunk_size - overlap
    return chunks


async def process_document(document_id: str) -> None:
    """Parse and chunk a document. A Redis worker should call this function in production."""
    async with SessionLocal() as session:
        document = await session.get(CurriculumDocument, document_id)
        if document is None:
            return
        document.status = DocumentStatus.PROCESSING
        await session.commit()
        try:
            source = await storage.read(document.object_key)
            extracted = extract_text(source, document.content_type)
            chunks = [
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=index,
                    content=chunk,
                    source_locator=locator,
                )
                for text, locator in extracted
                for index, chunk in enumerate(chunk_text(text))
            ]
            if not chunks:
                raise ValueError("The document contains no extractable text")
            await session.execute(
                delete(DocumentChunk).where(DocumentChunk.document_id == document.id)
            )
            session.add_all(chunks)
            document.status = DocumentStatus.READY
            document.failure_reason = None
        except Exception as exc:
            document.status = DocumentStatus.FAILED
            document.failure_reason = str(exc)
        await session.commit()

from uuid import UUID

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from education_platform.db.base import Base, UUIDTimestampMixin


class Conversation(UUIDTimestampMixin, Base):
    __tablename__ = "conversations"

    teacher_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    collection_id: Mapped[UUID] = mapped_column(ForeignKey("curriculum_collections.id"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="New conversation")


class ConversationMessage(UUIDTimestampMixin, Base):
    __tablename__ = "conversation_messages"

    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)


class MessageCitation(UUIDTimestampMixin, Base):
    __tablename__ = "message_citations"

    message_id: Mapped[UUID] = mapped_column(ForeignKey("conversation_messages.id"), index=True)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("curriculum_documents.id"))
    chunk_id: Mapped[UUID] = mapped_column(ForeignKey("document_chunks.id"))

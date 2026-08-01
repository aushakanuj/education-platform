import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from education_platform.db.base import Base, UUIDTimestampMixin


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    TEACHER = "teacher"


class Institution(UUIDTimestampMixin, Base):
    __tablename__ = "institutions"

    name: Mapped[str] = mapped_column(String(200), unique=True)


class User(UUIDTimestampMixin, Base):
    __tablename__ = "users"

    institution_id: Mapped[UUID] = mapped_column(ForeignKey("institutions.id"), index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), index=True)
    is_active: Mapped[bool] = mapped_column(default=True)


class RefreshSession(UUIDTimestampMixin, Base):
    __tablename__ = "refresh_sessions"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

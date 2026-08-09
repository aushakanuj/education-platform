"""Identity, tenancy, sessions, and audit models."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from education_platform.db.base import Base, UUIDPrimaryKeyMixin, UUIDTimestampMixin
from education_platform.db.types import JsonDict, partial_unique_index, str_enum


class InstitutionStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class UserStatus(str, enum.Enum):
    PROVISIONED = "provisioned"
    ACTIVE = "active"
    DEACTIVATED = "deactivated"
    ARCHIVED = "archived"


class RoleName(str, enum.Enum):
    ADMINISTRATOR = "administrator"
    TEACHER = "teacher"
    STUDENT = "student"


class StudentProfileStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class Institution(UUIDTimestampMixin, Base):
    __tablename__ = "institutions"

    name: Mapped[str] = mapped_column(String(200), unique=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    status: Mapped[InstitutionStatus] = mapped_column(
        str_enum(InstitutionStatus, "institution_status"),
        default=InstitutionStatus.ACTIVE,
    )


class User(UUIDTimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("institution_id", "email", name="uq_users_institution_email"),
    )

    institution_id: Mapped[UUID] = mapped_column(ForeignKey("institutions.id"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(Text)
    status: Mapped[UserStatus] = mapped_column(
        str_enum(UserStatus, "user_status"),
        default=UserStatus.PROVISIONED,
        index=True,
    )


class UserRole(UUIDTimestampMixin, Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role", name="uq_user_roles_user_role"),)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[RoleName] = mapped_column(str_enum(RoleName, "role_name"))


class StudentProfile(UUIDTimestampMixin, Base):
    __tablename__ = "student_profiles"
    __table_args__ = (
        UniqueConstraint(
            "institution_id",
            "student_identifier",
            name="uq_student_profiles_institution_identifier",
        ),
        partial_unique_index(
            "uq_student_profiles_user_id",
            "user_id",
            where="user_id IS NOT NULL",
        ),
    )

    institution_id: Mapped[UUID] = mapped_column(ForeignKey("institutions.id"), index=True)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    student_identifier: Mapped[str] = mapped_column(String(100))
    full_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[StudentProfileStatus] = mapped_column(
        str_enum(StudentProfileStatus, "student_profile_status"),
        default=StudentProfileStatus.ACTIVE,
    )


class RefreshSession(UUIDTimestampMixin, Base):
    __tablename__ = "refresh_sessions"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_events"

    institution_id: Mapped[UUID] = mapped_column(ForeignKey("institutions.id"), index=True)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[UUID | None] = mapped_column(nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonDict, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

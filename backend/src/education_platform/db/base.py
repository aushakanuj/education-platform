from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, MetaData, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        # No "ck" entry, deliberately: every CheckConstraint(...) in this codebase already
        # passes its complete, final name (e.g. name="ck_quiz_attempts_attempt_number"),
        # not a short suffix for a convention to expand. A "ck" convention here would
        # re-template that already-complete name a second time — substituting it whole
        # into %(constraint_name)s and prepending ck_%(table_name)s_ again — producing
        # e.g. ck_quiz_attempts_ck_quiz_attempts_attempt_number. This is exactly the
        # double-prefix bug migration d0e1f2a3b4c5 renames 19 existing constraints to
        # recover from; leaving this entry out is what stops the next one from happening.
        # If a future CheckConstraint call site ever wants convention-derived naming
        # instead of a self-contained name, add "ck" back *and* migrate every existing
        # CheckConstraint call site to pass a short suffix in the same change, not before.
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)


class Base(DeclarativeBase):
    metadata = metadata


class UUIDPrimaryKeyMixin:
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class UUIDTimestampMixin(UUIDPrimaryKeyMixin, TimestampMixin):
    """UUID primary key plus created/updated timestamps."""

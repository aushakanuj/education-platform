"""Authenticated caller identity. Services import this, not ``api.deps``."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: UUID
    institution_id: UUID
    email: str
    roles: frozenset[str]
    student_profile_id: UUID | None
    status: str

    @property
    def is_administrator(self) -> bool:
        return "administrator" in self.roles

    @property
    def is_student(self) -> bool:
        return "student" in self.roles

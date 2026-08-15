"""Pydantic contracts for RAG ingest trust boundaries (chunk → embed → upsert)."""

from __future__ import annotations

import json
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from education_platform.modules.rag.embeddings import embedding_dimensions
from education_platform.modules.rag.models import IngestTargetKind

DocKind = Literal["source_material", "knowledge_document"]
AllowedRole = Literal["administrator", "teacher", "student"]
_ALLOWED_ROLES = frozenset({"administrator", "teacher", "student"})


class TextChunk(BaseModel):
    """Validated chunk produced from Docling before DB persist."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ordinal: int = Field(ge=1)
    text: str = Field(min_length=1)
    content_hash: str = Field(min_length=64, max_length=64)
    token_count: int = Field(ge=0)
    page_number: int | None = Field(default=None, ge=1)
    section_heading: str | None = Field(default=None, max_length=500)

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("text must not be blank")
        return cleaned

    @field_validator("section_heading")
    @classmethod
    def strip_heading(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("content_hash")
    @classmethod
    def sha256_hex(cls, value: str) -> str:
        if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value.lower()):
            raise ValueError("content_hash must be a 64-char hex digest")
        return value.lower()


class VectorRow(BaseModel):
    """Validated embedding row before pgvector upsert."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: UUID
    embedding: list[float]
    doc_id: UUID
    doc_kind: DocKind
    institution_id: UUID
    required_roles: list[str] = Field(min_length=1)
    doc_type: str | None = None
    page_number: int | None = Field(default=None, ge=1)
    version_id: UUID

    @field_validator("embedding")
    @classmethod
    def embedding_dims(cls, value: list[float]) -> list[float]:
        expected = embedding_dimensions()
        if len(value) != expected:
            raise ValueError(f"embedding must have length {expected}, got {len(value)}")
        return value

    @field_validator("required_roles")
    @classmethod
    def roles_allowed(cls, value: list[str]) -> list[str]:
        cleaned = [role.strip() for role in value if role and role.strip()]
        if not cleaned:
            raise ValueError("required_roles must not be empty")
        unknown = [role for role in cleaned if role not in _ALLOWED_ROLES]
        if unknown:
            raise ValueError(f"unknown required_roles: {unknown}")
        return cleaned


class IngestJobClaim(BaseModel):
    """Validated claim handoff from queue → worker process."""

    model_config = ConfigDict(extra="ignore", from_attributes=True, frozen=True)

    id: UUID
    target_kind: IngestTargetKind
    target_id: UUID


class RequiredRoles(BaseModel):
    """Normalized role list from admin upload form input."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    roles: list[str] = Field(min_length=1)

    @field_validator("roles")
    @classmethod
    def normalize_roles(cls, value: list[str]) -> list[str]:
        cleaned = [role.strip() for role in value if role and str(role).strip()]
        if not cleaned:
            raise ValueError("roles must not be empty")
        unknown = [role for role in cleaned if role not in _ALLOWED_ROLES]
        if unknown:
            raise ValueError(f"unknown roles: {unknown}")
        # Preserve order, drop duplicates.
        seen: set[str] = set()
        ordered: list[str] = []
        for role in cleaned:
            if role not in seen:
                seen.add(role)
                ordered.append(role)
        return ordered


def parse_required_roles(raw: str | None) -> list[str]:
    """Parse upload-form roles JSON/CSV into a validated role list."""
    default = ["administrator", "teacher"]
    if raw is None or not raw.strip():
        return RequiredRoles(roles=default).roles
    text = raw.strip()
    roles: list[str]
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list) and all(isinstance(item, str) for item in parsed):
            roles = list(parsed) or default
        else:
            roles = default
    else:
        roles = [part.strip() for part in text.split(",") if part.strip()] or default
    return RequiredRoles(roles=roles).roles

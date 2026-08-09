"""Auth request/response schemas."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)
    institution_name: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class MeResponse(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str
    institution_id: UUID
    roles: list[str]
    student_profile_id: UUID | None
    status: str


class ProvisionStudentRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    student_identifier: str
    institution_name: str = "POC Demo School"

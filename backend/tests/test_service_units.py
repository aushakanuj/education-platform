"""Direct service-level tests to strengthen coverage."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from education_platform.api.deps import Principal
from education_platform.modules.academics.service import assert_can_access_subtopic
from education_platform.modules.auth.models import Institution
from education_platform.modules.auth.schemas import LoginRequest, ProvisionStudentRequest
from education_platform.modules.auth.service import login, provision_student
from education_platform.modules.materials.seed import seed_approved_materials
from education_platform.modules.materials.service import get_subtopic_by_slug


def _seed(session: Session) -> None:
    seed_approved_materials(session, replace=True)


@pytest.mark.asyncio
async def test_assert_access_admin_bypasses_enrollment(
    async_db_session: AsyncSession, db_session: Session
) -> None:
    _seed(db_session)
    subtopic = await get_subtopic_by_slug(async_db_session, "rectangles_squares_properties")
    institution = await async_db_session.scalar(select(Institution))
    assert institution is not None
    admin = Principal(
        user_id=subtopic.id,
        institution_id=institution.id,
        email="admin@example.com",
        roles=frozenset({"administrator"}),
        student_profile_id=None,
        status="active",
    )
    await assert_can_access_subtopic(async_db_session, admin, subtopic.id)


@pytest.mark.asyncio
async def test_provision_duplicate_rejected(
    async_db_session: AsyncSession, db_session: Session
) -> None:
    _seed(db_session)
    payload = ProvisionStudentRequest(
        email="dup@example.com",
        password="password123",
        full_name="Dup",
        student_identifier="DUP-1",
    )
    await provision_student(async_db_session, payload)
    with pytest.raises(HTTPException) as exc:
        await provision_student(async_db_session, payload)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_login_unknown_institution(
    async_db_session: AsyncSession, db_session: Session
) -> None:
    _seed(db_session)
    await provision_student(
        async_db_session,
        ProvisionStudentRequest(
            email="x@example.com",
            password="password123",
            full_name="X",
            student_identifier="X-1",
        ),
    )
    with pytest.raises(HTTPException) as exc:
        await login(
            async_db_session,
            LoginRequest(
                email="x@example.com",
                password="password123",
                institution_name="Missing School",
            ),
        )
    assert exc.value.status_code == 401

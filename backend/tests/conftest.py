"""Shared SQLite fixtures for database and API tests."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from education_platform.core.config import get_settings
from education_platform.db import models as _models
from education_platform.db.session import get_session, reset_engine
from education_platform.main import app
from education_platform.modules.materials.seed import seed_approved_materials

_ = _models

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
MATERIALS_DIR = REPO_ROOT / "docs" / "materials"

STUDENT_EMAIL = "student@example.com"
STUDENT_PASSWORD = "password123"


@pytest.fixture()
def sqlite_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture()
def migrated_db(sqlite_path: Path) -> Iterator[Path]:
    database_url = f"sqlite+aiosqlite:///{sqlite_path}"
    os.environ["DATABASE_URL"] = database_url
    os.environ["JWT_SECRET"] = "test-secret-key-at-least-32-bytes-long!!"
    get_settings.cache_clear()
    reset_engine()

    alembic_cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{sqlite_path}")
    command.upgrade(alembic_cfg, "head")

    sync_engine = create_engine(f"sqlite:///{sqlite_path}")

    @event.listens_for(sync_engine, "connect")
    def _fk(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    with sync_engine.connect() as conn:
        tables = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        ).fetchall()
        assert len(tables) >= 32

    sync_engine.dispose()
    yield sqlite_path

    reset_engine()
    get_settings.cache_clear()
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("JWT_SECRET", None)


@pytest.fixture()
def db_session(migrated_db: Path) -> Iterator[Session]:
    engine = create_engine(f"sqlite:///{migrated_db}")

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture()
def seeded_db(db_session: Session) -> Session:
    seeded = seed_approved_materials(db_session, MATERIALS_DIR, replace=True)
    assert "quadrilaterals" in seeded
    assert "squares_cubes_roots" in seeded
    return db_session


@pytest.fixture()
async def async_db_session(migrated_db: Path) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{migrated_db}")

    @event.listens_for(engine.sync_engine, "connect")
    def _fk(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture()
def client(seeded_db: Session, migrated_db: Path) -> Iterator[TestClient]:
    """HTTP client bound to a migrated + seeded temp SQLite database."""
    _ = seeded_db
    engine = create_async_engine(f"sqlite+aiosqlite:///{migrated_db}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override_session
    with TestClient(app, raise_server_exceptions=True) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    reset_engine()


@pytest.fixture()
def enrolled_student_headers(client: TestClient) -> dict[str, str]:
    provision = client.post(
        "/api/v1/auth/provision-student",
        json={
            "email": STUDENT_EMAIL,
            "password": STUDENT_PASSWORD,
            "full_name": "Test Student",
            "student_identifier": "S-100",
            "institution_name": "POC Demo School",
        },
    )
    assert provision.status_code == 200, provision.text
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": STUDENT_EMAIL,
            "password": STUDENT_PASSWORD,
            "institution_name": "POC Demo School",
        },
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    enroll = client.post(
        "/api/v1/me/enrollments/poc-math",
        json={"confirm": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert enroll.status_code == 200, enroll.text
    return {"Authorization": f"Bearer {token}"}

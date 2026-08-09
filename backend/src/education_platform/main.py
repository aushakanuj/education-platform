from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from education_platform.core.config import get_settings
from education_platform.db import models as _models
from education_platform.modules.academics.models import Subtopic
from education_platform.modules.academics.router import router as academics_router
from education_platform.modules.assessments.router import router as assessments_router
from education_platform.modules.auth.router import router as auth_router
from education_platform.modules.materials.router import router as materials_router
from education_platform.modules.materials.seed import seed_approved_materials

_ = _models


def _seed_if_empty() -> None:
    settings = get_settings()
    url = settings.database_url.replace("+aiosqlite", "")
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection: object, _record: object) -> None:
        if url.startswith("sqlite"):
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    with Session(engine) as session:
        has_topics = session.scalar(select(Subtopic.id).limit(1))
        if has_topics is None:
            seed_approved_materials(session, replace=True)
    engine.dispose()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    _seed_if_empty()
    yield


settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(academics_router, prefix=settings.api_v1_prefix)
app.include_router(materials_router, prefix=settings.api_v1_prefix)
app.include_router(assessments_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}

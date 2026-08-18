from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from education_platform.core.config import get_settings
from education_platform.db import models as _models
from education_platform.db.url import to_sync_url
from education_platform.modules.academics.router import router as academics_router
from education_platform.modules.assessments.router import router as assessments_router
from education_platform.modules.assistant.router import router as assistant_router
from education_platform.modules.audit.router import router as audit_router
from education_platform.modules.auth.router import router as auth_router
from education_platform.modules.authoring.router import router as authoring_router
from education_platform.modules.insights.router import router as insights_router
from education_platform.modules.materials.router import router as materials_router
from education_platform.modules.materials.seed import seed_approved_materials
from education_platform.modules.nl_query.router import router as nl_query_router
from education_platform.modules.rag.router import router as rag_router

_ = _models


def _seed_if_empty() -> None:
    settings = get_settings()
    engine = create_engine(to_sync_url(settings.database_url))
    with Session(engine) as session:
        seed_approved_materials(session, replace=False)
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
app.include_router(rag_router, prefix=settings.api_v1_prefix)
app.include_router(assistant_router, prefix=settings.api_v1_prefix)
app.include_router(assessments_router, prefix=settings.api_v1_prefix)
app.include_router(audit_router, prefix=settings.api_v1_prefix)
app.include_router(insights_router, prefix=settings.api_v1_prefix)
app.include_router(nl_query_router, prefix=settings.api_v1_prefix)
app.include_router(authoring_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}

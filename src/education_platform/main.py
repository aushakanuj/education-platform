from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from education_platform.core.config import get_settings
from education_platform.db.session import engine
from education_platform.modules.ai import models as ai_models
from education_platform.modules.ai.router import router as assistant_router
from education_platform.modules.auth import models as auth_models
from education_platform.modules.auth.router import router as auth_router
from education_platform.modules.curriculum import models as curriculum_models
from education_platform.modules.curriculum.router import router as curriculum_router

# Import models before metadata initialization.
_ = (ai_models, auth_models, curriculum_models)
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await engine.dispose()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(curriculum_router, prefix=settings.api_v1_prefix)
app.include_router(assistant_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", tags=["system"])
async def readiness() -> dict[str, str]:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return {"status": "ready"}

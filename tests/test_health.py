import asyncio

from fastapi.testclient import TestClient

from education_platform.db.base import Base
from education_platform.db.session import engine
from education_platform.main import app


def test_health_and_readiness() -> None:
    async def create_schema() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(create_schema())
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/ready").json() == {"status": "ready"}

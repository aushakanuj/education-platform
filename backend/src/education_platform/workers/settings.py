"""ARQ worker settings for RAG ingest jobs."""

from __future__ import annotations

from arq.connections import RedisSettings

from education_platform.core.config import get_settings
from education_platform.workers.ingest import process_ingest_job


class WorkerSettings:
    functions = [process_ingest_job]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 1

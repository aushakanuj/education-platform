"""Postgres-backed ingest worker: claim queued jobs with SKIP LOCKED."""

from __future__ import annotations

import logging
import time
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from education_platform.db import models as _orm_tables
from education_platform.db.session import sync_session
from education_platform.modules.generation.adk import CurriculumRunner
from education_platform.modules.generation.curriculum_worker import (
    claim_next_curriculum_job,
    process_curriculum_job_sync,
)
from education_platform.modules.generation.items import ItemsWriter
from education_platform.modules.generation.lesson import TopicLessonWriter
from education_platform.modules.generation.outline import OutlineWriter
from education_platform.modules.generation.worker import (
    claim_next_generation_job,
    process_generation_job_sync,
)
from education_platform.modules.rag.models import IngestJob, IngestJobStatus
from education_platform.workers.ingest import ParsePdfFn, process_ingest_job_sync

_ = _orm_tables  # register FK targets (users) for the worker process

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL_SECONDS = 1.5


def _sync_session() -> Session:
    return sync_session()


def claim_next_job(session: Session) -> UUID | None:
    """Claim one queued ingest job using ``FOR UPDATE SKIP LOCKED``.

    Marks the row ``running`` and commits so the lock is released before processing.
    """
    job = session.scalar(
        select(IngestJob)
        .where(IngestJob.status == IngestJobStatus.QUEUED)
        .order_by(IngestJob.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        return None
    job.status = IngestJobStatus.RUNNING
    job_id = job.id
    session.commit()
    return job_id


def poll_once(
    *,
    parse_pdf: ParsePdfFn | None = None,
    write_outline: OutlineWriter | None = None,
    write_items: ItemsWriter | None = None,
    write_lesson: TopicLessonWriter | None = None,
    curriculum_runner: CurriculumRunner | None = None,
    session: Session | None = None,
) -> UUID | None:
    """Claim at most one ingest, topic-generation, or curriculum-generation job."""
    owns_session = session is None
    db = session or _sync_session()
    try:
        job_id = claim_next_job(db)
        if job_id is not None:
            process_ingest_job_sync(str(job_id), parse_pdf=parse_pdf)
            return job_id
        gen_id = claim_next_generation_job(db)
        if gen_id is not None:
            process_generation_job_sync(
                gen_id,
                write_outline=write_outline,
                write_items=write_items,
                write_lesson=write_lesson,
            )
            return gen_id
        curriculum_id = claim_next_curriculum_job(db)
        if curriculum_id is None:
            return None
        process_curriculum_job_sync(curriculum_id, runner=curriculum_runner)
        return curriculum_id
    finally:
        if owns_session:
            db.close()


def run_forever(*, poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS) -> None:
    """Poll ingest_jobs, then generation_jobs, then curriculum_generation_jobs."""
    logging.basicConfig(level=logging.INFO)
    logger.info(
        "Worker started (poll every %.1fs; ingest, generation, then curriculum jobs)",
        poll_interval_seconds,
    )
    while True:
        claimed = poll_once()
        if claimed is None:
            time.sleep(poll_interval_seconds)

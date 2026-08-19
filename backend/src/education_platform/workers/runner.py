"""Postgres-backed ingest worker: claim queued jobs with SKIP LOCKED."""

from __future__ import annotations

import logging
import time
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from education_platform.db.session import sync_session
from education_platform.modules.rag.models import IngestJob, IngestJobStatus
from education_platform.workers.ingest import ParsePdfFn, process_ingest_job_sync

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
    session: Session | None = None,
) -> UUID | None:
    """Claim at most one job and process it. Returns the claimed job id, if any."""
    owns_session = session is None
    db = session or _sync_session()
    try:
        job_id = claim_next_job(db)
        if job_id is None:
            return None
        process_ingest_job_sync(str(job_id), parse_pdf=parse_pdf)
        return job_id
    finally:
        if owns_session:
            db.close()


def run_forever(*, poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS) -> None:
    """Poll ``ingest_jobs`` until interrupted."""
    logging.basicConfig(level=logging.INFO)
    logger.info(
        "Ingest worker started (poll every %.1fs; queue=Postgres ingest_jobs)",
        poll_interval_seconds,
    )
    while True:
        claimed = poll_once()
        if claimed is None:
            time.sleep(poll_interval_seconds)

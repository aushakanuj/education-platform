"""Claim and process admin ADK curriculum generation jobs."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from education_platform.core.config import get_settings
from education_platform.db.session import sync_session
from education_platform.modules.generation.adk import (
    MISSING_OPENROUTER_MESSAGE,
    NO_INGESTED_CHUNKS_MESSAGE,
    CurriculumRunner,
)
from education_platform.modules.generation.curriculum import (
    build_adk_request,
    fail_curriculum_job,
    ingested_chunks_for_subtopic,
    persist_approved_curriculum,
)
from education_platform.modules.generation.models import CurriculumGenerationJob
from education_platform.modules.generation.types import GenerationJobStatus

logger = logging.getLogger(__name__)


def claim_next_curriculum_job(session: Session) -> UUID | None:
    """FOR UPDATE SKIP LOCKED on curriculum_generation_jobs status=queued."""
    job = session.scalar(
        select(CurriculumGenerationJob)
        .where(CurriculumGenerationJob.status == GenerationJobStatus.QUEUED)
        .order_by(CurriculumGenerationJob.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        return None
    job.status = GenerationJobStatus.RUNNING
    job_id = job.id
    session.commit()
    return job_id


def _resolve_runner(runner: CurriculumRunner | None) -> CurriculumRunner | str:
    if runner is not None:
        return runner
    if not get_settings().openrouter_configured:
        return MISSING_OPENROUTER_MESSAGE
    # Live ADK is imported only when a job actually needs the model, so unit tests
    # that inject a fake CurriculumRunner never construct google.adk agents.
    from education_platform.modules.generation.adk_live import LiveAdkRunner

    return LiveAdkRunner()


def process_curriculum_job_sync(
    job_id: UUID,
    *,
    runner: CurriculumRunner | None = None,
) -> None:
    session = sync_session()
    try:
        job = session.get(CurriculumGenerationJob, job_id)
        if job is None:
            logger.error("Curriculum generation job %s not found", job_id)
            return
        job.status = GenerationJobStatus.RUNNING
        session.commit()
        chunks = ingested_chunks_for_subtopic(session, job.subtopic_id)
        if not chunks:
            fail_curriculum_job(job, NO_INGESTED_CHUNKS_MESSAGE)
            session.commit()
            return
        resolved = _resolve_runner(runner)
        if isinstance(resolved, str):
            fail_curriculum_job(job, resolved)
            session.commit()
            return
        request = build_adk_request(session, job, chunks)
        if isinstance(request, str):
            fail_curriculum_job(job, request)
            session.commit()
            return
        result = resolved.generate(request)
        job.round_count = result.round_count
        job.reviewer_notes = result.reviewer_notes or None
        job.transcript = result.transcript
        gate = persist_approved_curriculum(session, job, result)
        if gate is not None:
            session.rollback()
            job = session.get(CurriculumGenerationJob, job_id)
            if job is None:
                return
            fail_curriculum_job(job, gate, result=result)
        session.commit()
    except Exception as exc:
        logger.exception("Curriculum generation job %s failed", job_id)
        session.rollback()
        job = session.get(CurriculumGenerationJob, job_id)
        if job is not None:
            fail_curriculum_job(job, str(exc)[:2000])
            session.commit()
    finally:
        session.close()

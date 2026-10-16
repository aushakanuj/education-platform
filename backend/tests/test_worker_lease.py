"""Workers reclaim jobs left stuck in running, up to a retry limit."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from education_platform.core.config import get_settings
from education_platform.modules.academics.models import Subtopic
from education_platform.modules.auth.models import User
from education_platform.modules.generation.models import ContentGenerationRun, GenerationJob
from education_platform.modules.generation.types import (
    GenerationJobKind,
    GenerationJobStatus,
    RunPhase,
)
from education_platform.modules.generation.worker import claim_next_generation_job
from education_platform.workers.lease import Claimed, claim, heartbeat
from test_generation import SEEDED_SLUG


def _generation_job(
    session: Session,
    *,
    status: GenerationJobStatus,
    attempts: int,
    locked_until: datetime | None,
    max_attempts: int = 3,
) -> tuple[ContentGenerationRun, GenerationJob]:
    settings = get_settings()
    subtopic = session.scalar(select(Subtopic).where(Subtopic.slug == SEEDED_SLUG))
    assert subtopic is not None
    admin = session.scalar(select(User).where(User.email == settings.demo_admin_email))
    assert admin is not None
    run = ContentGenerationRun(
        topic_id=subtopic.topic_id,
        submitted_by_user_id=admin.id,
        title="Lease",
        phase=RunPhase.GENERATING,
        target_item_count=60,
    )
    session.add(run)
    session.flush()
    job = GenerationJob(
        run_id=run.id,
        kind=GenerationJobKind.LESSON,
        status=status,
        attempts=attempts,
        max_attempts=max_attempts,
        locked_until=locked_until,
    )
    session.add(job)
    session.commit()
    return run, job


def test_stale_running_job_is_reclaimed_and_attempts_increment(seeded_db: Session) -> None:
    _run, job = _generation_job(
        seeded_db,
        status=GenerationJobStatus.RUNNING,
        attempts=1,
        locked_until=datetime.now(UTC) - timedelta(minutes=5),
    )
    claimed = claim_next_generation_job(seeded_db)
    assert claimed == job.id
    seeded_db.expire_all()
    refreshed = seeded_db.get(GenerationJob, job.id)
    assert refreshed is not None
    assert refreshed.status is GenerationJobStatus.RUNNING
    assert refreshed.attempts == 2
    assert refreshed.locked_until is not None
    assert refreshed.locked_until > datetime.now(UTC)


def test_exhausted_job_fails_its_run(seeded_db: Session) -> None:
    run, job = _generation_job(
        seeded_db,
        status=GenerationJobStatus.RUNNING,
        attempts=3,
        locked_until=datetime.now(UTC) - timedelta(minutes=5),
    )
    assert claim_next_generation_job(seeded_db) is None
    seeded_db.expire_all()
    failed_run = seeded_db.get(ContentGenerationRun, run.id)
    assert failed_run is not None
    assert failed_run.phase is RunPhase.FAILED
    assert failed_run.failure_reason == "Worker lost this job 3 times"
    refreshed = seeded_db.get(GenerationJob, job.id)
    assert refreshed is not None
    assert refreshed.status is GenerationJobStatus.FAILED
    assert refreshed.attempts == 3


def test_running_job_without_a_lease_is_reclaimed(seeded_db: Session) -> None:
    """Rows already running when the lease column was added have a null lock."""
    _run, job = _generation_job(
        seeded_db,
        status=GenerationJobStatus.RUNNING,
        attempts=0,
        locked_until=None,
    )
    claimed = claim_next_generation_job(seeded_db)
    assert claimed == job.id
    seeded_db.expire_all()
    refreshed = seeded_db.get(GenerationJob, job.id)
    assert refreshed is not None
    assert refreshed.status is GenerationJobStatus.RUNNING
    assert refreshed.attempts == 1
    assert refreshed.locked_until is not None


def test_fresh_lease_is_not_claimed(seeded_db: Session) -> None:
    _run, job = _generation_job(
        seeded_db,
        status=GenerationJobStatus.RUNNING,
        attempts=1,
        locked_until=datetime.now(UTC) + timedelta(minutes=5),
    )
    assert claim(seeded_db, GenerationJob) is None
    assert claim_next_generation_job(seeded_db) is None
    seeded_db.expire_all()
    refreshed = seeded_db.get(GenerationJob, job.id)
    assert refreshed is not None
    assert refreshed.status is GenerationJobStatus.RUNNING
    assert refreshed.attempts == 1


def test_heartbeat_extends_locked_until(
    seeded_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WORKER_LEASE_SECONDS", "1")
    get_settings.cache_clear()
    _run, job = _generation_job(
        seeded_db,
        status=GenerationJobStatus.QUEUED,
        attempts=0,
        locked_until=None,
    )
    result = claim(seeded_db, GenerationJob)
    assert isinstance(result, Claimed)
    assert result.job_id == job.id
    seeded_db.expire_all()
    before = seeded_db.get(GenerationJob, job.id)
    assert before is not None and before.locked_until is not None
    started = before.locked_until
    with heartbeat(GenerationJob, job.id):
        time.sleep(1.5)
    seeded_db.expire_all()
    after = seeded_db.get(GenerationJob, job.id)
    assert after is not None and after.locked_until is not None
    assert after.locked_until > started
    get_settings.cache_clear()

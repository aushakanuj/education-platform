from __future__ import annotations

from enum import StrEnum

from education_platform.modules.generation.schemas import GenerationRunOut
from education_platform.modules.generation.types import RunPhase
from education_platform.modules.progress.types import ProgressSnapshot
from education_platform.modules.rag.schemas import (
    KnowledgeVersionStatusOut,
    MaterialVersionStatusOut,
)

_RUN_TRUE_TERMINAL = frozenset({RunPhase.PUBLISHED, RunPhase.FAILED, RunPhase.DISCARDED})
_RUN_HITL = frozenset({RunPhase.OUTLINE_REVIEW, RunPhase.QA_REVIEW})
_RUN_WORKER = frozenset({RunPhase.INDEXING, RunPhase.OUTLINING, RunPhase.GENERATING})
_VERSION_TERMINAL = frozenset({"ready", "failed", "published", "superseded", "archived"})


class GenerationDisposition(StrEnum):
    WORKER_MOVING = "worker_moving"
    REWRITE_RUNNING = "rewrite_running"
    HITL_PARK = "hitl_park"
    TERMINAL = "terminal"


class IngestDisposition(StrEnum):
    PROCESSING = "processing"
    TERMINAL = "terminal"


def jobs_in_flight(snapshot: GenerationRunOut) -> bool:
    return any(job.status in ("queued", "running") for job in snapshot.jobs)


def generation_disposition(snapshot: GenerationRunOut) -> GenerationDisposition:
    if snapshot.phase in _RUN_TRUE_TERMINAL:
        return GenerationDisposition.TERMINAL
    if snapshot.phase in _RUN_WORKER:
        return GenerationDisposition.WORKER_MOVING
    if snapshot.phase in _RUN_HITL:
        if jobs_in_flight(snapshot):
            return GenerationDisposition.REWRITE_RUNNING
        return GenerationDisposition.HITL_PARK
    return GenerationDisposition.WORKER_MOVING


def ingest_disposition(lifecycle_status: str) -> IngestDisposition:
    if lifecycle_status in _VERSION_TERMINAL:
        return IngestDisposition.TERMINAL
    return IngestDisposition.PROCESSING


def should_close(snapshot: ProgressSnapshot) -> bool:
    if isinstance(snapshot, GenerationRunOut):
        return generation_disposition(snapshot) is GenerationDisposition.TERMINAL
    if isinstance(snapshot, (MaterialVersionStatusOut, KnowledgeVersionStatusOut)):
        return ingest_disposition(snapshot.lifecycle_status) is IngestDisposition.TERMINAL
    raise TypeError(f"Unsupported snapshot type: {type(snapshot)!r}")

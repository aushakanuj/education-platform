# Shape

Data structures first. Public callers import `LessonProposal` and the five service operations in `usage.md`. Persistence stays on `SourceMaterialVersion` (slug `"lesson"`). The domain type is a projection with a real phase machine — not `READY` plus a pile of nullables.

## State machine

One proposal is one `SourceMaterialVersion` row whose `submitted_by_user_id` is set. Student visibility is still only `published` ∧ non-empty `content_markdown`.

```text
                    submit_pdf
                         |
                         v
                   ┌───────────┐
         ┌─────────│ PROCESSING │─────────┐
         │         └─────┬─────┘          │
         │  index fail   │ index+chunks   │ generate fail
         │               │                │ (lesson markdown invalid / LLM down)
         v               v                v
     ┌────────┐   complete_from_chunks  ┌────────┐
     │ FAILED │          |              │ FAILED │
     └────────┘          v              └────────┘
               ┌──────────────────┐
               │ AWAITING_APPROVAL│  markdown required; unpublished
               └────────┬─────────┘
            approve │         │ discard
                    v         v
            ┌───────────┐  ┌──────────┐
            │ PUBLISHED │  │ ARCHIVED │
            └─────┬─────┘  └──────────┘
                  │ later approve of a newer proposal
                  v
            ┌────────────┐
            │ SUPERSEDED │
            └────────────┘
```

Public `ProposalPhase` collapses worker internals:

| Phase            | Stored `lifecycle_status` | Markdown | Students see it |
| ---------------- | ------------------------- | -------- | --------------- |
| `processing`     | `processing`              | none     | no              |
| `awaiting_review`| `awaiting_approval`       | required | no              |
| `failed`         | `failed`                  | —        | no              |
| `published`      | `published`               | required | yes             |
| `discarded`      | `archived`                | —        | no              |

`READY` is **not** on this machine. It remains admin index-complete (no markdown, no approval UI). Overloading `READY` would make `IngestStatusBadge` lie.

Job row: `succeeded` iff the version is `awaiting_approval` (generate path) or `ready` (admin path). `failed` tracks version `failed`. The worker never writes `published`.

Invariants encoded in the database, not comments:

- Partial unique already: one `published` version per `source_material_id`.
- New partial unique: at most one version per `source_material_id` where `lifecycle_status IN ('processing', 'awaiting_approval')`. One in-flight proposal (or admin index) at a time on that lesson.
- Check: `awaiting_approval` ⇒ `content_markdown IS NOT NULL AND length > 0`.
- Check: `submitted_by_user_id IS NOT NULL` for any row that is or was a proposal (`awaiting_approval` or archived/published descendants of submit). Seed and admin index leave the column null.
- Approve is idempotent: `published` + same id → no-op. Discard of `archived` → no-op. Approve of `archived`/`failed`/`processing` → domain error.

Quiz is a passenger on the same phase, not a second boolean:

- While `processing` / `failed`: no student quiz change.
- On successful generate: optional `QuizVersion(DRAFT)` + `QuizItem`s + `QuestionVersion(DRAFT)` bound to this material version. Not released.
- On approve: if a draft quiz is bound, publish those question versions, set quiz `released`, open `QuizRelease`, keep `QuizMaterialBinding`.
- On discard: archive the draft quiz version and its draft question versions. Seeded released quizzes stay.
- If lesson markdown succeeds and quiz LLM/validation fails: still `awaiting_approval` with `quiz=None`. Lesson is the product; quiz is best-effort.

## Domain types

```python
# modules/proposals/types.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID

from education_platform.modules.materials.markdown_parser import ParsedSlide


class ProposalPhase(str, Enum):
    PROCESSING = "processing"
    AWAITING_REVIEW = "awaiting_review"
    FAILED = "failed"
    PUBLISHED = "published"
    DISCARDED = "discarded"


@dataclass(frozen=True, slots=True)
class ProposalQuizQuestion:
    prompt: str
    options: dict[str, str]  # A–D
    correct_label: str       # teacher preview only; never copied onto student quiz GET
    explanation: str


@dataclass(frozen=True, slots=True)
class ProposalQuiz:
    quiz_version_id: UUID
    questions: tuple[ProposalQuizQuestion, ...]


@dataclass(frozen=True, slots=True)
class LessonProposal:
    """Caller-facing unit. id == SourceMaterialVersion.id."""

    id: UUID
    subtopic_id: UUID
    source_material_id: UUID
    title: str
    phase: ProposalPhase
    version_number: int
    submitted_by_user_id: UUID
    failure_reason: str | None
    created_at: datetime
    markdown: str | None          # set from awaiting_review onward (and published)
    slides: tuple[ParsedSlide, ...]
    quiz: ProposalQuiz | None

    def is_reviewable(self) -> bool:
        return self.phase is ProposalPhase.AWAITING_REVIEW


@dataclass(frozen=True, slots=True)
class GeneratedLesson:
    """Pure result of LLM + parse. Not a row."""

    title: str
    markdown: str
    slides: tuple[ParsedSlide, ...]


@dataclass(frozen=True, slots=True)
class GeneratedQuiz:
    questions: tuple[ProposalQuizQuestion, ...]


class ProposalError(Exception):
    """Safe to show a teacher. status_code 403/404/409/400."""

    def __init__(self, detail: str, *, status_code: int = 403) -> None: ...
```

HTTP adapters (`ProposalAcceptedOut`, `ProposalOut`, `ProposalPreviewOut`) live in `schemas.py` and are **not** imported by the worker or by `materials` student reads.

## Persistence additions (same tables)

`SourceMaterialVersion` (materials/models.py):

- `submitted_by_user_id: UUID | None` (FK `users.id`)
- enum value `AWAITING_APPROVAL = "awaiting_approval"`
- partial unique `uq_source_material_versions_one_in_flight` on `source_material_id` where `lifecycle_status IN ('processing', 'awaiting_approval')`
- check `ck_source_material_versions_awaiting_has_markdown`

No new `IngestTargetKind`. `target_id` remains the version UUID. Generation intent is `submitted_by_user_id is not None` — the same column the review UI uses for “who uploaded,” so we do not sync a parallel flag.

Chunk embeddings for proposal versions use `required_roles=["teacher", "administrator"]` only. Students study markdown slides, not unpublished PDF chunks. Admin index-only path keeps today’s roles (out of this change except as a known leak).

## Signatures

```python
# modules/proposals/service.py — async HTTP boundary
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from education_platform.modules.authorization.principal import Principal
from education_platform.modules.authorization.scope import Scope
from education_platform.modules.proposals.types import LessonProposal

PROPOSAL_QUIZ_SIZE = 5  # small released quiz; not Bloom/80-item

async def submit_pdf(
    session: AsyncSession,
    scope: Scope,
    principal: Principal,
    *,
    subtopic_id: UUID,
    title: str,
    file: UploadFile,
) -> LessonProposal:
    """Authorize taught offering (or unrestricted admin), reject a second in-flight
    proposal (409), store blob, attach to SourceMaterial slug 'lesson', enqueue
    ingest_jobs. Returns phase=processing. Does not generate markdown here.
    """
    raise NotImplementedError


async def get_proposal(
    session: AsyncSession,
    scope: Scope,
    proposal_id: UUID,
) -> LessonProposal:
    """Load + authorize. Maps stored status → ProposalPhase. Includes quiz+keys
    when phase is awaiting_review | published (teacher/admin only).
    """
    raise NotImplementedError


async def list_proposals(
    session: AsyncSession,
    scope: Scope,
    subtopic_id: UUID,
) -> list[LessonProposal]:
    """In-flight first, then recent failed/published/discarded for this subtopic.
    Authorize like authoring._authorised_subtopic (taught_offering_ids).
    """
    raise NotImplementedError


async def approve(
    session: AsyncSession,
    scope: Scope,
    principal: Principal,
    proposal_id: UUID,
) -> LessonProposal:
    """Human gate. Requires awaiting_review (or already published → return as-is).
    Supersedes the current published 'lesson' version (seed checksum path).
    Releases bound draft quiz if present. Audits. Never called by the worker.
    """
    raise NotImplementedError


async def discard(
    session: AsyncSession,
    scope: Scope,
    principal: Principal,
    proposal_id: UUID,
) -> None:
    """Archive awaiting_review (or no-op if already archived). Processing/failed
    cannot be discarded — wait for fail, or leave the in-flight unique to expire
    as failed. Failed versions do not block a new submit (not in-flight).
    """
    raise NotImplementedError
```

```python
# modules/proposals/generate.py — sync, called only from the worker
from sqlalchemy.orm import Session

from education_platform.modules.materials.models import SourceMaterialVersion
from education_platform.modules.proposals.types import GeneratedLesson, GeneratedQuiz

LessonWriter = Callable[[LessonGeneratePrompt], GeneratedLesson]
QuizWriter = Callable[[QuizGeneratePrompt], GeneratedQuiz]


def complete_from_chunks(
    session: Session,
    version: SourceMaterialVersion,
    *,
    write_lesson: LessonWriter | None = None,
    write_quiz: QuizWriter | None = None,
) -> None:
    """Precondition: chunks persisted, embeddings written, submitted_by_user_id set.
    Writes content_markdown, validates parse_slides >= 1, optional draft quiz,
    sets awaiting_approval. On lesson failure sets failed + failure_reason.
    Quiz failure is logged; proposal still awaits review without quiz.
    Does not commit — caller (ingest) commits with the job row.
    """
    raise NotImplementedError


def _default_lesson_writer(prompt: LessonGeneratePrompt) -> GeneratedLesson:
    # TODO: chat_completion_json_sync; require ## Slide N — Title headings
    # TODO: parse_slides; if empty, raise so complete_from_chunks marks failed
    raise NotImplementedError


def render_lesson_prompt(*, subtopic_name: str, outcomes: list[str], chunk_texts: list[str]) -> str:
    """Pure. Chunk text is untrusted; never concatenated into a system instruction
    as commands. Same stance as design 04 §6.
    """
    raise NotImplementedError
```

```python
# modules/rag/queue.py — shared enqueue, used by admin upload and submit_pdf
async def queue_source_material_pdf(
    session: AsyncSession,
    *,
    subtopic_id: UUID,
    title: str,
    data: bytes,
    content_type: str,
    filename: str,
    institution_id: UUID,
    submitted_by_user_id: UUID | None,
) -> SourceMaterialVersion:
    """Find-or-create SourceMaterial(slug='lesson'), next version_number,
    PROCESSING row, IngestJob(SOURCE_MATERIAL_VERSION), blob already stored by caller.
    submitted_by_user_id None => admin index-only (today's upload_curriculum_material).
    """
    raise NotImplementedError
```

Admin `upload_curriculum_material` keeps its institution check and audit, then calls `queue_source_material_pdf(..., submitted_by_user_id=None)`. `submit_pdf` checks teaching scope + in-flight, then the same helper with the teacher’s user id. Neither function is a pass-through of the other: each owns a different authorization and terminal status.

```python
# core/llm.py addition
def chat_completion_json_sync(...) -> dict[str, Any]:
    """httpx/OpenAI sync client for the ingest worker. Same model settings as async."""
    raise NotImplementedError
```

Worker change (pseudocode, same file, not a new microservice):

```python
def _process_source_material(session, job, parse):
    # ... existing parse / chunk / persist ...
    if version.submitted_by_user_id is not None:
        required_roles = ["teacher", "administrator"]  # not student
        # persist embeddings with those roles
        complete_from_chunks(session, version)
    else:
        required_roles = ["student", "teacher", "administrator"]  # current admin path
        version.lifecycle_status = READY
    job.status = SUCCEEDED
    session.commit()
```

Approve (pseudocode):

```python
async def approve(session, scope, principal, proposal_id):
    proposal = await _authorised_proposal(session, scope, proposal_id)
    if proposal.phase is ProposalPhase.PUBLISHED:
        return proposal  # idempotent
    if proposal.phase is not ProposalPhase.AWAITING_REVIEW:
        raise ProposalError("Only a proposal waiting for review can be approved.")
    version = await session.get(SourceMaterialVersion, proposal.id)
    current = published_on_same_material(session, version.source_material_id)
    if current is not None and current.id != version.id:
        current.lifecycle_status = SUPERSEDED  # seed pattern; students now follow this version
    version.lifecycle_status = PUBLISHED
    version.published_at = now
    material.status = PUBLISHED
    await _release_bound_draft_quiz(session, version, principal.user_id)
    await record_event(..., AuditAction.MATERIAL_PUBLISHED)  # add enum value
    # TODO: do not rewrite student_material_progress; directory already follows latest published
```

## Module map

```text
modules/proposals/                 # NEW — human gate + generation policy (deep)
  types.py                         # LessonProposal, ProposalPhase, GeneratedLesson
  service.py                       # submit, get, list, approve, discard (async)
  generate.py                      # complete_from_chunks, prompts, sync LLM (worker)
  router.py                        # /teaching/... thin adapters
  schemas.py                       # HTTP models only

modules/rag/
  queue.py                         # NEW — shared PDF version + ingest_jobs insert
  service.py                       # admin upload calls queue(..., submitted_by=None)
  models.py                        # unchanged target kinds

modules/materials/
  models.py                        # submitted_by_user_id, AWAITING_APPROVAL, indexes
  queries.py                       # published_material_version UNCHANGED
  service.py                       # student GET UNCHANGED
  seed_content.py                  # still publishes slug "lesson" directly

modules/authoring/service.py       # list_questions skips versions that already have QuizItems
                                   # (proposal drafts must not appear as bank Approve targets)

workers/ingest.py                  # after embed: complete_from_chunks if submitted_by set
core/llm.py                        # chat_completion_json_sync
frontend/
  api/teachingProposals.ts
  pages/teacher/LessonProposalsPage.tsx   # /teacher/lessons
  components/TeacherShell.tsx             # rail item next to question bank
  pages/teacher/SubjectMaterialsPage.tsx  # no change — published catalog only
```

Call chain for the happy path (≤3 hops after the router):

```text
router.submit → proposals.submit_pdf → rag.queue_source_material_pdf
worker → ingest._process_source_material → proposals.complete_from_chunks
router.approve → proposals.approve → materials supersede + assessments release
```

## Deliberately not done

- No LangGraph, Redis, MinIO, Docling-as-a-service, second worker process, or new `IngestTargetKind`.
- No supervisor inbox; approver is the teacher of the offering or an unrestricted admin on the same routes.
- No resolver change and no second slug. A published `"teacher-lesson"` would race `published_material_version` (max `version_number` across the subtopic).
- No auto-publish. `READY` stays index-only.
- No section-scoped materials. Approve is grade–subject common source, same as seed.
- Authoring `publish_draft` is not reused for lessons (it does not attach `QuizItem`s and would skip the material gate).
- Student quiz GET still has no answer keys. Preview keys exist only on `/teaching/lesson-proposals/{id}/preview`.
- Progress stays “always latest published” (current code). Design 04’s bound-old-version behavior is not in this change.
- POC Demo School teacher seed is test/synthetic data’s problem, not this module’s.

# Shape

Derived from `usage.md`. Callers import domain types from `generation.types` and operations from `generation.service` / `generation.worker`. HTTP schemas live in `generation.schemas` and are not re-exported.

## Data structures

### `DraftPhase` — the generation+approval lifecycle

One enum. Not `ready AND markdown is not None`. Not ingest-job status. The HTTP UI polls this.

```python
class DraftPhase(StrEnum):
    PROCESSING = "processing"           # upload accepted; worker owns the row
    AWAITING_REVIEW = "awaiting_review" # indexed + valid lesson markdown; students cannot see it
    PUBLISHED = "published"             # student-visible; supersedes previous published lesson
    FAILED = "failed"                   # index or synthesis failed; chunks may exist for retry
    DISCARDED = "discarded"             # human rejected; never student-visible
```

Projection from `SourceMaterialVersion.lifecycle_status` (existing enum, **no new DB values**):

| Storage `lifecycle_status` | `content_markdown` | `DraftPhase` |
| --- | --- | --- |
| `processing` | any | `PROCESSING` |
| `ready` | non-empty, parseable slides | `AWAITING_REVIEW` |
| `published` | non-empty | `PUBLISHED` |
| `failed` | any | `FAILED` |
| `archived` | any | `DISCARDED` |
| `superseded` | — | not listed in the teacher inbox (historical) |
| `ready` + empty markdown | — | **invariant violation** for `LESSON_DRAFT`; `project()` raises. Admin index-only `SOURCE_MATERIAL_VERSION` rows are not drafts and never enter this module. |

`SourceMaterialVersionStatus.DRAFT` is unused by this path (upload inserts `processing`).

### State machine

```text
                    submit_pdf
                        |
                        v
                   PROCESSING
                   /         \
          finish ok           finish/index fail
                 /             \
                v               v
        AWAITING_REVIEW       FAILED
           /         \         /    \
      approve      discard  retry   discard
         /             \     /         \
        v               v   v           v
    PUBLISHED        DISCARDED     PROCESSING
```

Illegal transitions raise `GenerationError` (403/409), they do not no-op except the two idempotent cases below.

Idempotent:

- `approve` of an already-`PUBLISHED` **this** version returns the same `PublishedLesson`.
- `discard` of an already-`DISCARDED` version returns.

Not idempotent as success:

- `approve` of `FAILED` / `PROCESSING` / `DISCARDED` → error.
- `discard` of `PUBLISHED` or `PROCESSING` → error (`PROCESSING` is owned by the worker).
- `retry` only from `FAILED`.
- `submit_pdf` always mints a new version. Same PDF checksum does not coalesce (matches current admin ingest).

Approve of version B while version A is published: A becomes `superseded`, B becomes `published`. The partial unique index `uq_source_material_versions_one_published` is the write lock. A unique-violation is a 409, not a second published row.

Students read `published_material_version` only. They keep the seeded lesson through `PROCESSING`, `FAILED`, `AWAITING_REVIEW`, and `DISCARDED`.

### Domain types

```python
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class DraftPhase(StrEnum):
    PROCESSING = "processing"
    AWAITING_REVIEW = "awaiting_review"
    PUBLISHED = "published"
    FAILED = "failed"
    DISCARDED = "discarded"


@dataclass(frozen=True, slots=True)
class Slide:
    number: int
    title: str
    content: str


@dataclass(frozen=True, slots=True)
class LessonMarkdown:
    """Validated student-study markdown. Constructor is the only way to mint one."""

    title: str
    body: str
    slides: tuple[Slide, ...]

    def __post_init__(self) -> None:
        if not self.slides:
            raise ValueError("lesson markdown must contain at least one ## Slide N heading")


@dataclass(frozen=True, slots=True)
class LessonDraft:
    draft_id: UUID          # SourceMaterialVersion.id
    subtopic_id: UUID
    title: str
    phase: DraftPhase
    markdown: LessonMarkdown | None   # set iff AWAITING_REVIEW or PUBLISHED
    failure_reason: str | None        # set iff FAILED
    version_number: int
    chunk_count: int
    created_at: datetime

    def __post_init__(self) -> None:
        if self.phase in {DraftPhase.AWAITING_REVIEW, DraftPhase.PUBLISHED}:
            if self.markdown is None:
                raise ValueError(f"{self.phase} requires markdown")
        if self.phase is DraftPhase.FAILED and not self.failure_reason:
            raise ValueError("failed drafts require a reason")


@dataclass(frozen=True, slots=True)
class AcceptedDraft:
    draft_id: UUID
    subtopic_id: UUID
    phase: DraftPhase  # always PROCESSING on submit / retry enqueue


@dataclass(frozen=True, slots=True)
class PublishedLesson:
    draft_id: UUID
    subtopic_id: UUID
    title: str
    markdown: LessonMarkdown
    quiz_released: bool
    quiz_id: UUID | None
    question_count: int


class GenerationError(DomainError):
    """Safe to show a teacher. status_code 403 (scope) or 409 (illegal phase)."""
```

`LessonMarkdown.from_body(body: str, *, fallback_title: str) -> LessonMarkdown` wraps `materials.markdown_parser.parse_lesson`. Invalid slide headings fail closed (version `FAILED` in the worker; 500 only if a `ready` row is corrupt at read time).

Wire types (`AcceptedDraftOut`, `LessonDraftOut`, `PublishedLessonOut`) are Pydantic adapters on the router. They are not imported by the worker, tests of synthesize, or assessments.

### Storage mapping (private)

Reuse existing rows. No `lesson_drafts` table.

- `SourceMaterial.slug == "lesson"` for the subtopic. Same parent the seed uses. Resolver unchanged.
- New `SourceMaterialVersion`: `lifecycle_status=processing`, `content_format="pdf"`, blob + checksum of the PDF, `content_markdown=None`.
- `IngestJob(target_kind=LESSON_DRAFT, target_id=version.id, status=queued)`.
- After worker success: `content_markdown` set, `lifecycle_status=ready`. Blob remains the PDF; format stays `"pdf"` (the file on disk is still a PDF).
- Embeddings for this version: `required_roles=["teacher","administrator"]` until approve, then `["student","teacher","administrator"]`.
- Quiz on approve: existing `Question` / `QuestionVersion` / `QuizItem` / `QuizVersion` / `QuizRelease` / `QuizMaterialBinding`. New `QuizVersion` is `released` with an `open` release. Previous latest released quiz remains in history; `released_quiz` already picks max `version_number`.

New Alembic: add `lesson_draft` to `IngestTargetKind` and the `ck_ingest_jobs_target_kind` check. No new version-status enum values.

---

## Function signatures

### `generation/types.py`

```python
def project(version: SourceMaterialVersion, *, subtopic_id: UUID, chunk_count: int) -> LessonDraft:
    """Map a version row to a draft. Raises if a LESSON_DRAFT ready row has no slides."""
    raise NotImplementedError
```

### `generation/synthesize.py` (pure)

```python
from collections.abc import Sequence
from education_platform.modules.rag.chunking import TextChunk  # domain chunk, already validated


def slides_from_chunks(
    chunks: Sequence[TextChunk],
    *,
    title: str,
    outcomes: Sequence[str],
) -> LessonMarkdown:
    """Heuristic lesson: one slide per section_heading (fallback: packed token windows).
    Used when OPENROUTER_API_KEY is missing, and as the validator's expected shape.
    """
    raise NotImplementedError


def lesson_from_llm_body(body: str, *, fallback_title: str) -> LessonMarkdown:
    """Parse and reject bodies that do not satisfy parse_lesson / ≥1 slide."""
    raise NotImplementedError
```

LLM I/O is not in the public service surface. The worker injects a writer:

```python
LessonWriter = Callable[[str], str]  # prompt → markdown body


def write_lesson(
    chunks: Sequence[TextChunk],
    *,
    title: str,
    subject: str,
    grade: str,
    outcomes: Sequence[str],
    writer: LessonWriter | None,
) -> LessonMarkdown:
    """If writer is None, return slides_from_chunks. Else write, then lesson_from_llm_body.
    On parse failure, fall back once to slides_from_chunks rather than failing the index.
    # TODO: prompt must treat chunk text as untrusted data, never as instructions.
    """
    raise NotImplementedError
```

### `generation/service.py` (async HTTP)

```python
async def submit_pdf(
    session: AsyncSession,
    scope: Scope,
    principal: Principal,
    *,
    subtopic_id: UUID,
    title: str,
    file: UploadFile,
) -> AcceptedDraft:
    """Authorize taught offering (or unrestricted). Store blob, mint processing version
    on slug 'lesson', enqueue LESSON_DRAFT. Does not wait for the worker.
    """
    raise NotImplementedError


async def get_draft(session: AsyncSession, scope: Scope, draft_id: UUID) -> LessonDraft:
    raise NotImplementedError


async def list_drafts(
    session: AsyncSession, scope: Scope, subtopic_id: UUID
) -> list[LessonDraft]:
    """PROCESSING, AWAITING_REVIEW, FAILED for this subtopic. Newest first.
    Excludes PUBLISHED, DISCARDED, SUPERSEDED.
    """
    raise NotImplementedError


async def approve(
    session: AsyncSession,
    scope: Scope,
    principal: Principal,
    draft_id: UUID,
) -> PublishedLesson:
    """AWAITING_REVIEW → PUBLISHED. Supersede the previous published version on this
    material. Open student retrieval on this version's embeddings. Release a 5-question
    subtopic quiz bound to this version. Idempotent if already published.
    """
    raise NotImplementedError


async def discard(
    session: AsyncSession, scope: Scope, principal: Principal, draft_id: UUID
) -> None:
    """AWAITING_REVIEW or FAILED → ARCHIVED. Idempotent if already archived.
    PROCESSING is rejected: the worker still owns the row.
    """
    raise NotImplementedError


async def retry(
    session: AsyncSession, scope: Scope, principal: Principal, draft_id: UUID
) -> AcceptedDraft:
    """FAILED → PROCESSING and enqueue a new LESSON_DRAFT job for the same version.
    Worker skips Docling when chunks already exist.
    """
    raise NotImplementedError
```

### `generation/worker.py` (sync, ingest process)

```python
def finish_lesson_draft(session: Session, job: IngestJob) -> None:
    """After chunks+embeddings exist: synthesize markdown, validate slides, READY.
    On failure: version FAILED, job FAILED, chunks retained. Never PUBLISHED.
    """
    raise NotImplementedError
```

### `assessments/release.py` (sync-or-async helper owned by assessments)

```python
APPROVE_QUIZ_COUNT = 5


def release_generated_quiz(
    session: Session,
    *,
    subtopic_id: UUID,
    material_version_id: UUID,
    questions: Sequence[authoring.DraftQuestion],
    released_by_user_id: UUID,
) -> tuple[UUID, int]:
    """Persist published QuestionVersions, mint QuizVersion RELEASED, QuizItems,
    QuizMaterialBinding, open QuizRelease. Return (quiz_id, item_count).
    Empty questions → no-op, return (None-equivalent handled by caller).
    # TODO: find-or-create CommonMasteryQuiz for the subtopic (seed already does).
    """
    raise NotImplementedError
```

Generation `approve` calls this after the material row is published. It does not inline quiz SQL. Authoring `generate_questions` is **not** called: that writes unbound drafts into the question-bank inbox.

Approve-time quiz generation (async, in `generation/service.py`):

```python
async def _questions_for_approved_lesson(
    session: AsyncSession,
    *,
    subtopic_id: UUID,
    markdown: LessonMarkdown,
) -> list[DraftQuestion]:
    """Prompt with slide titles + outcomes. Validate with authoring.validate.
    OpenRouter missing → return []. Approve still succeeds with quiz_released=False.
    """
    raise NotImplementedError
```

Quiz is generated **on approve**, not in the worker. The human gate is the lesson. The quiz is a small released derivative bound to the version just published. Preview is lesson-only.

### RAG intake (extract, used by admin upload and generation)

```python
# rag/intake.py — not a new HTTP surface
async def accept_source_pdf(
    session: AsyncSession,
    *,
    institution_id: UUID,
    subtopic_id: UUID,
    title: str,
    file: UploadFile,
    target_kind: IngestTargetKind,
) -> tuple[SourceMaterial, SourceMaterialVersion, IngestJob]:
    """Validate PDF, store blob, find-or-create slug=lesson, insert processing version,
    enqueue job. Caller supplies target_kind (SOURCE_MATERIAL_VERSION vs LESSON_DRAFT).
    """
    raise NotImplementedError
```

Today this logic lives in `upload_curriculum_material`. Admin upload keeps calling it with `SOURCE_MATERIAL_VERSION`. Generation `submit_pdf` calls it with `LESSON_DRAFT` after scope checks. That is not a pass-through: generation adds assignment authorization, domain projection, and lesson-specific audit.

### Worker helpers (existing function grows two parameters)

```python
def _process_source_material(
    session: Session,
    job: IngestJob,
    parse: ParsePdfFn,
    *,
    required_roles: list[str] | None = None,
    skip_if_chunks_exist: bool = False,
) -> None:
    # default required_roles remain ["student","teacher","administrator"] for admin index
    # LESSON_DRAFT passes teacher+administrator and skip_if_chunks_exist=True
    raise NotImplementedError  # existing body + the two branches
```

---

## Module map

```text
generation/                    # owns lesson-draft lifecycle + markdown synthesis
  types.py                     # DraftPhase, LessonDraft, LessonMarkdown, errors
  synthesize.py                # chunks → LessonMarkdown (heuristic + LLM parse)
  service.py                   # submit / get / list / approve / discard / retry
  worker.py                    # finish_lesson_draft (sync)
  router.py                    # thin HTTP; wire schemas only
  schemas.py                   # Pydantic outs; from_domain adapters

rag/
  intake.py                    # accept_source_pdf (extracted from service.upload_*)
  models.py                    # IngestTargetKind.LESSON_DRAFT
  vector_store.py              # set_required_roles(version_id, roles)  # TODO

workers/ingest.py              # dispatch LESSON_DRAFT → index then finish_lesson_draft

assessments/release.py         # release_generated_quiz (tables this module already owns)

authoring/service.py           # reuse validate() + DraftQuestion only; no publish_draft

materials/queries.py           # unchanged published_material_version
materials/service.py           # unchanged student GET

frontend/
  api/generation.ts
  pages/teacher/LessonDraftsPage.tsx
  App.tsx + TeacherShell.tsx   # /teacher/lessons
  pages/teacher/SubjectMaterialsPage.tsx  # untouched (published preview)
```

Call chain for the three operations (≤3 files each):

- Submit: `router` → `generation.service.submit_pdf` → `rag.intake.accept_source_pdf`
- Worker: `workers.ingest` → `_process_source_material` → `generation.worker.finish_lesson_draft` → `synthesize.write_lesson`
- Approve: `router` → `generation.service.approve` → `assessments.release.release_generated_quiz`

---

## Invariants encoded in types vs checked at the boundary

Encoded:

- `AWAITING_REVIEW` / `PUBLISHED` cannot exist without `LessonMarkdown`.
- `LessonMarkdown` cannot exist without slides that `parse_slides` accepts.
- `DraftPhase` is the only status callers see.
- Partial unique: one published version per `source_material_id`.

Boundary (`_authorised_draft`, same pattern as authoring `_authorised_subtopic`):

- Institution match.
- `scope.unrestricted or offering_id in scope.taught_offering_ids`.
- Subtopic exists.
- Version belongs to slug `"lesson"` (a knowledge-doc id is 404, not 500).

Deliberately not done:

- No LangGraph, Redis, MinIO, second process, or Docling HTTP service.
- No supervisor inbox. Approver = teacher of the offering, or any administrator.
- No new material slug. No resolver change.
- No `GENERATING` status. Index + synthesis are one `PROCESSING` interval.
- No auto-publish.
- No section-scoped materials.
- Student quiz GET still does not join answer keys. Teacher draft GET does not return a quiz.
- Dual-role users still resolve as unrestricted admins (`scope_for` unchanged). They may approve via this API; they do not load teaching assignments.

---

## Pseudocode for load-bearing paths

### `submit_pdf`

```python
async def submit_pdf(...):
    subtopic, offering_id = await _authorised_subtopic(session, scope, subtopic_id)
    material, version, job = await rag_intake.accept_source_pdf(
        session,
        institution_id=scope.institution_id,
        subtopic_id=subtopic.id,
        title=title,
        file=file,
        target_kind=IngestTargetKind.LESSON_DRAFT,
    )
    await record_event(..., entity_type="lesson_draft", entity_id=version.id)
    return AcceptedDraft(draft_id=version.id, subtopic_id=subtopic.id, phase=DraftPhase.PROCESSING)
```

### `finish_lesson_draft`

```python
def finish_lesson_draft(session, job):
    version = session.get(SourceMaterialVersion, job.target_id)
    chunks = load_chunks_ordered(session, version.id)
    if not chunks:
        _fail(session, job, version, "No extractable text")
        return
    title, subject, grade, outcomes = load_subtopic_context(session, version)
    try:
        markdown = write_lesson(chunks, title=title, subject=subject, grade=grade, outcomes=outcomes, writer=_sync_llm_or_none())
    except Exception as exc:
        _fail(session, job, version, str(exc)[:2000])
        return
    version.content_markdown = markdown.body
    version.title = markdown.title
    version.lifecycle_status = SourceMaterialVersionStatus.READY
    version.failure_reason = None
    job.status = IngestJobStatus.SUCCEEDED
    job.error = None
    session.commit()
```

### `approve`

```python
async def approve(...):
    draft = await get_draft(session, scope, draft_id)
    if draft.phase is DraftPhase.PUBLISHED:
        return await _published_view(session, draft)  # idempotent
    if draft.phase is not DraftPhase.AWAITING_REVIEW:
        raise GenerationError("Only a lesson waiting for review can be approved.", 409)
    version = await session.get(SourceMaterialVersion, draft.draft_id)
    previous = await published_on_same_material(session, version.source_material_id)
    if previous is not None and previous.id != version.id:
        previous.lifecycle_status = SourceMaterialVersionStatus.SUPERSEDED
    version.lifecycle_status = SourceMaterialVersionStatus.PUBLISHED
    version.published_at = datetime.now(UTC)
    parent = await session.get(SourceMaterial, version.source_material_id)
    parent.status = SourceMaterialStatus.PUBLISHED
    await vector_store.set_required_roles(version.id, ["student", "teacher", "administrator"])
    questions = await _questions_for_approved_lesson(session, subtopic_id=draft.subtopic_id, markdown=draft.markdown)
    quiz_id, count = (None, 0)
    if questions:
        quiz_id, count = await asyncio.to_thread(
            release_generated_quiz, ..., questions=questions, released_by_user_id=principal.user_id
        )
    await record_event(..., event_type=MATERIAL_PUBLISHED)  # TODO: add audit action if missing
    return PublishedLesson(...)
```

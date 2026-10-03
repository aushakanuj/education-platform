# Shape

Derived from `usage.md`. Callers import domain types from `generation.types` and operations from `generation.service` / `generation.worker`. HTTP schemas live in `generation.schemas` and are not re-exported. ORM lives in `generation.models` and is imported from `db.models` so Alembic sees it.

The workflow aggregate is **`GenerationRun`**. Intake PDF is a topic-scoped `SourceMaterialVersion` that ends **READY**. Outline nodes are **run children** until accept. Draft Subtopic rows are not the HITL document. Student-facing published lesson + released `topic_mastery` quiz are written only at HITL 2 publish.

## Data structures

### `RunPhase` — the workflow lifecycle

One enum, stored on `content_generation_runs.phase`. Not projected from `SourceMaterialVersion.lifecycle_status`. Not ingest-job status. The HTTP UI polls this.

```python
class RunPhase(StrEnum):
    INDEXING = "indexing"               # ingest_jobs owns the PDF
    OUTLINING = "outlining"             # generation_jobs kind=outline owns the DAG write
    OUTLINE_REVIEW = "outline_review"   # HITL 1; PATCH + accept
    GENERATING = "generating"           # slice 2–3: items + lesson jobs; slice 1 stops here with no jobs
    QA_REVIEW = "qa_review"             # HITL 2
    PUBLISHED = "published"             # student-visible copies exist
    FAILED = "failed"                   # ingest or a generation job failed
    DISCARDED = "discarded"             # human abandoned; never student-visible
```

In-flight (blocks a second submit on the same topic):

```python
IN_FLIGHT_PHASES = frozenset({
    RunPhase.INDEXING,
    RunPhase.OUTLINING,
    RunPhase.OUTLINE_REVIEW,
    RunPhase.GENERATING,
    RunPhase.QA_REVIEW,
})
```

`failed`, `discarded`, and `published` are terminal for the unique index. A new submit after failure is allowed without a discard endpoint in slice 1.

### State machine

```text
                         submit_pdf
                             |
                             v
                         INDEXING
                        /         \
            intake READY           ingest fail
                   /                    \
                  v                      v
              OUTLINING               FAILED
             /         \
     outline ok      outline fail
            /               \
           v                 v
    OUTLINE_REVIEW         FAILED
      /          \
patch (stay)   accept
                  |
                  v
             GENERATING  ---- slice 1: no jobs, park here
                  |
         slice 2–3 jobs succeed
                  |
                  v
              QA_REVIEW
             /         \
        publish      reject_items
           /               \
          v                 v
      PUBLISHED         GENERATING
```

`discard` (later) is legal from `outline_review`, `qa_review`, `failed`. Illegal while a worker owns the row (`indexing` / `outlining` / `generating`).

Illegal transitions raise `GenerationError` (403/409). They do not no-op except:

- `accept_outline` of a run already `generating` / `qa_review` / `published` with frozen nodes returns the current `GenerationRun` (double-click).
- `publish` of an already-`published` **this** run returns the same `PublishedTopic`.
- `patch_outline` with the same document is a replacement no-op in effect.

Not idempotent as success:

- `submit_pdf` always mints a new run and a new intake version. Same PDF checksum does not coalesce.
- `submit_pdf` while `IN_FLIGHT_PHASES` on that topic → 409.
- `patch_outline` / first `accept_outline` only from `outline_review`.
- `accept_outline` of `failed` / `indexing` / `outlining` → 409.

Students read published SMV / released quiz only. They keep the seeded catalog through every phase until `published`.

### Domain types

```python
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from education_platform.core.errors import DomainError


class RunPhase(StrEnum):
    INDEXING = "indexing"
    OUTLINING = "outlining"
    OUTLINE_REVIEW = "outline_review"
    GENERATING = "generating"
    QA_REVIEW = "qa_review"
    PUBLISHED = "published"
    FAILED = "failed"
    DISCARDED = "discarded"


class GenerationJobKind(StrEnum):
    OUTLINE = "outline"                 # slice 1
    ITEMS = "items"                     # slice 2
    LESSON = "lesson"                   # slice 3
    REGENERATE_ITEMS = "regenerate_items"  # slice 4


class GenerationJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ItemCount:
    """Teacher-settable bank size. Constructor is the clamp."""

    value: int

    def __post_init__(self) -> None:
        if not 60 <= self.value <= 80:
            raise ValueError("target_item_count must be between 60 and 80")

    @classmethod
    def parse(cls, raw: int | None) -> ItemCount:
        return cls(80 if raw is None else int(raw))


@dataclass(frozen=True, slots=True)
class ProposedOutcome:
    statement: str

    def __post_init__(self) -> None:
        if not self.statement.strip():
            raise ValueError("outcome statement must be non-empty")


@dataclass(frozen=True, slots=True)
class OutlineNode:
    """Run-local DAG node. Not a Subtopic. accepted_subtopic_id is None until accept."""

    id: UUID
    parent_id: UUID | None
    slug: str
    title: str
    token_mass: int
    prerequisite_score: Decimal  # 0–1, LLM
    centrality: Decimal          # 0–1, graph
    weight: Decimal              # editable combined weight; need not sum to 1 until accept
    quota: int | None            # None → derive on read; frozen on accept
    matched_subtopic_id: UUID | None
    force_create: bool
    accepted_subtopic_id: UUID | None
    proposed_outcomes: tuple[ProposedOutcome, ...]
    sequence: int

    def __post_init__(self) -> None:
        if self.weight < 0:
            raise ValueError("weight must be >= 0")
        if self.quota is not None and self.quota < 0:
            raise ValueError("quota must be >= 0")
        if self.force_create and self.matched_subtopic_id is not None:
            raise ValueError("force_create cannot carry a matched_subtopic_id")
        if len(self.proposed_outcomes) > 3:
            raise ValueError("at most 3 proposed outcomes per node")


@dataclass(frozen=True, slots=True)
class OutlineDocument:
    """HITL 1 document. The live node list is the spec; PATCH replaces it."""

    target_item_count: ItemCount
    nodes: tuple[OutlineNode, ...]

    def preview_quotas(self) -> tuple[int, ...]:
        """Largest Remainder over normalized weights. Used by GET before accept."""
        raise NotImplementedError  # delegate to outline.largest_remainder

    def normalized_weights(self) -> tuple[Decimal, ...]:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class OutlinePatch:
    """Caller-supplied replacement. Node ids must already belong to the run.
    Omitting a current node drops it. New ids are rejected (teacher does not mint nodes).
    To merge two nodes, drop one and fold its weight/title into the other.
    """

    target_item_count: ItemCount | None
    nodes: tuple[OutlineNodeEdit, ...]


@dataclass(frozen=True, slots=True)
class OutlineNodeEdit:
    id: UUID
    parent_id: UUID | None
    slug: str
    title: str
    weight: Decimal
    matched_subtopic_id: UUID | None
    force_create: bool
    proposed_outcomes: tuple[str, ...]
    sequence: int


@dataclass(frozen=True, slots=True)
class GenerationRun:
    id: UUID
    topic_id: UUID
    title: str
    phase: RunPhase
    target_item_count: ItemCount
    submitted_by_user_id: UUID
    intake_version_id: UUID | None
    failure_reason: str | None
    outline: OutlineDocument | None   # set from outlining-complete onward (empty tuple while outlining)
    draft_lesson_markdown: str | None  # slice 3; None in slice 1
    published_lesson_version_id: UUID | None
    published_quiz_version_id: UUID | None
    created_at: datetime

    def __post_init__(self) -> None:
        if self.phase is RunPhase.FAILED and not self.failure_reason:
            raise ValueError("failed runs require a reason")
        if self.phase is RunPhase.OUTLINE_REVIEW:
            if self.outline is None or not self.outline.nodes:
                raise ValueError("outline_review requires nodes")
        if self.phase is RunPhase.PUBLISHED:
            if self.published_lesson_version_id is None or self.published_quiz_version_id is None:
                raise ValueError("published runs require lesson and quiz version ids")


@dataclass(frozen=True, slots=True)
class AcceptedRun:
    run_id: UUID
    topic_id: UUID
    phase: RunPhase  # always INDEXING on submit


@dataclass(frozen=True, slots=True)
class PublishedTopic:
    run_id: UUID
    topic_id: UUID
    lesson_version_id: UUID
    quiz_version_id: UUID
    item_count: int


@dataclass(frozen=True, slots=True)
class HeadingCluster:
    """Pure input to outline: distinct Docling headings + token mass."""

    heading: str
    token_mass: int
    sample_texts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProposedOutline:
    """Pure LLM/heuristic result. Not rows. Worker persists it onto the run."""

    nodes: tuple[ProposedOutlineNode, ...]


@dataclass(frozen=True, slots=True)
class ProposedOutlineNode:
    key: str
    parent_key: str | None
    slug: str
    title: str
    token_mass: int
    prerequisite_score: Decimal
    centrality: Decimal
    proposed_outcomes: tuple[str, ...]


class GenerationError(DomainError):
    """Safe to show a teacher. 403 scope, 404 missing, 409 illegal phase / in-flight."""
```

Wire types (`AcceptedRunOut`, `GenerationRunOut`, `OutlinePatchIn`) are Pydantic adapters on the router. They are not imported by the worker or by `outline.py`. GET serializes `quota` as the preview value when the stored quota is still null.

### Storage mapping (private)

New tables:

```text
content_generation_runs
  id
  topic_id                  FK topics NOT NULL
  submitted_by_user_id      FK users NOT NULL
  title                     VARCHAR(200)
  phase                     VARCHAR  (RunPhase)
  target_item_count         INT  CHECK 60–80
  failure_reason            TEXT NULL
  intake_source_material_version_id   FK source_material_versions NULL
  draft_quiz_version_id     FK quiz_versions NULL          -- slice 2
  draft_lesson_markdown     TEXT NULL                      -- slice 3
  published_lesson_version_id FK source_material_versions NULL  -- slice 4
  published_quiz_version_id FK quiz_versions NULL          -- slice 4
  created_at / updated_at
  PARTIAL UNIQUE (topic_id) WHERE phase IN (indexing, outlining, outline_review, generating, qa_review)

content_generation_outline_nodes
  id
  run_id                    FK runs ON DELETE CASCADE
  parent_id                 FK self NULL
  slug, title
  token_mass                INT
  prerequisite_score        NUMERIC
  centrality                NUMERIC
  weight                    NUMERIC
  quota                     INT NULL          -- frozen on accept
  matched_subtopic_id       FK subtopics NULL
  force_create              BOOL
  accepted_subtopic_id      FK subtopics NULL -- set on accept
  proposed_outcomes         JSON  (list[str], 1–3)
  sequence                  INT
  UNIQUE (run_id, slug)

generation_jobs
  id
  run_id                    FK runs
  kind                      VARCHAR  (GenerationJobKind)
  status                    VARCHAR  (queued|running|succeeded|failed)
  payload                   JSON NULL   -- slice 4: { "question_ids": [...] }
  error                     TEXT NULL
  created_at / updated_at
  INDEX (status, created_at)
  PARTIAL UNIQUE (run_id, kind) WHERE kind = 'outline' AND status IN ('queued', 'running')
```

Intake PDF (existing tables, topic XOR):

- `source_materials.topic_id` XOR `subtopic_id` (mirror `common_mastery_quizzes`). Drop `uq_source_materials_subtopic_slug`. Two partial uniques: `(subtopic_id, slug)` and `(topic_id, slug)`.
- Intake parent: `topic_id` set, `subtopic_id` NULL, `slug = "source"`. Never published. Chunks `required_roles = ["teacher", "administrator"]` because the parent is topic-scoped, not because `submitted_by_user_id` is set.
- New `SourceMaterialVersion`: `lifecycle_status=processing` → worker → **READY**. `content_format="pdf"`. `content_markdown` stays NULL. `submitted_by_user_id` set for audit only; it is **not** the workflow marker.
- `IngestJob(target_kind=SOURCE_MATERIAL_VERSION, target_id=version.id)`. Same kind as admin ingest.

Published student lesson (slice 4 only):

- Separate parent: same `topic_id`, `slug = "lesson"`, created at publish. Version `published` with markdown copied from `draft_lesson_markdown`. Worker never writes this row.

Drop as the product lock:

- Partial unique `uq_source_material_versions_one_in_flight_proposal`.
- Generation's use of `awaiting_approval`. Leave the enum value and the markdown CHECK so leftover rows do not break; no new writer.

Admin ingest: still subtopic `slug="lesson"`, `submitted_by_user_id IS NULL`, READY, student+teacher+admin embeddings.

### Schema facts this design honors

- `source_materials` today requires `subtopic_id` — XOR is slice-1 Alembic, required for topic intake.
- `published_material_version` stays subtopic-scoped. Slice 4 adds `published_topic_material_version`.
- One `CommonMasteryQuiz` per topic (`uq_common_mastery_quizzes_topic`). Slice 2 find-or-creates it; slice 4 releases a version. This pipeline does not emit `subtopic_mastery`.
- `Question.subtopic_id` + `question_outcome_tags` required on every generated item — possible only after accept has frozen `accepted_subtopic_id` and inserted outcomes.
- `IngestTargetKind` stays “which table.” Adding a kind that still points at `source_material_versions` is forbidden.

---

## Function signatures

### `generation/outline.py` (pure)

```python
from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from education_platform.modules.academics.models import Subtopic


def largest_remainder(weights: Sequence[Decimal], n: int) -> tuple[int, ...]:
    """Integer quotas that sum to n. Hamilton / largest-remainder.
    Zero-weight nodes get 0. All-zero weights raise ValueError.
    Tie-break: original order (Alpha before Gamma in the 0.8/0.4/0.8 example
    still assigns the two remainders to Alpha and Gamma because they are the
    two largest; equal remainders go to earlier sequence).
    Unit test: weights (0.46, 0.33, 0.21), n=80 → (37, 26, 17).
    """
    raise NotImplementedError


def combined_weight(*, token_mass: int, prerequisite_score: Decimal, centrality: Decimal) -> Decimal:
    """Linear blend then left unnormalized. Worker writes this as node.weight.
    # TODO: equal coefficients unless product later weights the three factors.
    """
    raise NotImplementedError


def outline_from_headings(clusters: Sequence[HeadingCluster]) -> ProposedOutline:
    """Heuristic DAG: one node per heading, parent_key=None, prerequisite=0.5,
    centrality from position, outcomes empty (accept will still require 1–3 —
    worker fills a single stub from the heading if LLM is missing).
    """
    raise NotImplementedError


def parse_proposed_outline(payload: dict[str, object]) -> ProposedOutline:
    """Boundary parse of LLM JSON. Invalid → ValueError, not a half-graph."""
    raise NotImplementedError


def match_existing_subtopics(
    proposed: ProposedOutline,
    existing: Sequence[Subtopic],
) -> tuple[UUID | None, ...]:
    """Per node: slug match under the topic, else casefold name match, else None.
    Does not insert rows.
    """
    raise NotImplementedError


def assert_dag(nodes: Sequence[OutlineNodeEdit]) -> None:
    """Reject unknown parent_id, cycles, duplicate ids. Called from patch_outline."""
    raise NotImplementedError
```

LLM I/O is not on the public service surface. The worker injects:

```python
OutlineWriter = Callable[[Sequence[HeadingCluster]], ProposedOutline]


def write_outline(
    clusters: Sequence[HeadingCluster],
    *,
    writer: OutlineWriter | None,
) -> ProposedOutline:
    """If writer is None and OpenRouter is configured, default LLM writer.
    If OpenRouter is missing, outline_from_headings.
    # TODO: prompt treats heading text + excerpts as untrusted data, never instructions.
    # TODO: instruct consolidate / expand / prerequisite order; JSON DAG schema.
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
    topic_id: UUID,
    title: str,
    file: UploadFile,
    target_item_count: int | None = None,
) -> AcceptedRun:
    """Authorize taught offering (or unrestricted). Reject in-flight run on
    this topic (409). Store blob, insert run(phase=indexing), find-or-create
    topic slug=source, PROCESSING version, ingest_jobs row. Does not wait.
    """
    raise NotImplementedError


async def submit_pdf_for_subtopic_alias(
    session: AsyncSession,
    scope: Scope,
    principal: Principal,
    *,
    subtopic_id: UUID,
    title: str,
    file: UploadFile,
) -> AcceptedRun:
    """Deprecated. Resolve parent topic_id, then submit_pdf. The path leaf is
    not matched_subtopic_id and not the lesson home.
    """
    raise NotImplementedError


async def get_run(session: AsyncSession, scope: Scope, run_id: UUID) -> GenerationRun:
    """Authorize via the run's topic. Project outline with preview quotas."""
    raise NotImplementedError


async def list_runs(
    session: AsyncSession, scope: Scope, topic_id: UUID
) -> list[GenerationRun]:
    """In-flight first, then created_at desc. Includes failed/published."""
    raise NotImplementedError


async def patch_outline(
    session: AsyncSession,
    scope: Scope,
    run_id: UUID,
    patch: OutlinePatch,
) -> GenerationRun:
    """outline_review only. Replace editable fields of existing nodes; delete
    omitted nodes. Re-preview quotas. No Subtopic writes. No Largest Remainder
    freeze.
    """
    raise NotImplementedError


async def accept_outline(
    session: AsyncSession,
    scope: Scope,
    principal: Principal,
    run_id: UUID,
) -> GenerationRun:
    """outline_review → generating.
    Normalize weights, freeze quotas via largest_remainder.
    Match-or-create Subtopic (flat sequenced list; DAG stays on nodes).
    Insert LearningOutcome stubs from proposed_outcomes (skip duplicate statements).
    Stamp accepted_subtopic_id. Idempotent if already past accept.
    Slice 1: do not insert generation_jobs for items/lesson.
    Slice 2: same function also enqueues kind=items and kind=lesson.
    """
    raise NotImplementedError
```

Slice 4 signatures are in `usage.md`. They stay in this module, not a second `publish.py` service — same aggregate, later time.

### `generation/worker.py` (sync, ingest process)

```python
def on_intake_indexed(session: Session, version_id: UUID) -> None:
    """If a run in indexing points at this version: phase=outlining, insert
    generation_jobs(kind=outline, queued). No-op for admin ingest.
    Must run in the same commit as version READY.
    """
    raise NotImplementedError


def fail_run_for_intake(session: Session, version_id: UUID, reason: str) -> None:
    """If a run in indexing points at this version: phase=failed, copy reason."""
    raise NotImplementedError


def claim_next_generation_job(session: Session) -> UUID | None:
    """FOR UPDATE SKIP LOCKED on generation_jobs status=queued. Mark running, commit."""
    raise NotImplementedError


def process_generation_job_sync(
    job_id: UUID,
    *,
    write_outline: OutlineWriter | None = None,
    write_items: ItemsWriter | None = None,    # slice 2
    write_lesson: TopicLessonWriter | None = None,  # slice 3
) -> None:
    """Dispatch on kind. Slice 1 implements OUTLINE only; other kinds log+fail
    until their slice. Never sets published.
    """
    raise NotImplementedError


def _finish_outline(session: Session, run_id: UUID, *, writer: OutlineWriter | None) -> None:
    """Load chunks for intake_version_id, cluster by section_heading, write_outline,
    match_existing_subtopics, persist nodes, phase=outline_review.
    On exception: run FAILED, job FAILED, intake stays READY.
    """
    raise NotImplementedError
```

### `rag/queue.py` (sibling, not a new target kind)

```python
async def queue_topic_intake_pdf(
    session: AsyncSession,
    *,
    topic_id: UUID,
    title: str,
    data: bytes,
    content_type: str,
    object_key: str,
    submitted_by_user_id: UUID,
) -> QueuedSourceMaterialPdf:
    """Find-or-create topic-scoped slug='source'. PROCESSING version.
    IngestTargetKind.SOURCE_MATERIAL_VERSION. Caller stored the blob.
    """
    raise NotImplementedError
```

Existing `queue_source_material_pdf` stays subtopic + slug `lesson` + optional null submitter. Do not add `topic_id: UUID | None` to that function — two grains, two functions, shared `_insert_processing_version`.

### `materials/queries.py` (slice 4)

```python
async def published_topic_material_version(
    session: AsyncSession, topic_id: UUID
) -> SourceMaterialVersion | None:
    raise NotImplementedError
```

### Slice 2–3 sketches (not implemented in slice 1)

```python
# generation/items.py (pure schemas; instructor arrives in slice 2)

class BloomLevel(StrEnum):
    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"
    ANALYZE = "analyze"


@dataclass(frozen=True, slots=True)
class GeneratedItem:
    subtopic_id: UUID
    learning_outcome_ids: tuple[UUID, ...]
    prompt: str
    options: dict[str, str]  # A–D
    correct_label: str
    correct_rationale: str
    distractor_rationales: dict[str, str]
    bloom: BloomLevel


def bloom_mix_for_quota(quota: int, *, heavy: bool) -> tuple[BloomLevel, ...]:
    """Lighter nodes → more Remember/Understand; heavy → Apply/Analyze."""
    raise NotImplementedError


# persist DRAFT Question + QuestionVersion + options + QuestionAnswerKey
# (correct_rationale / distractor_rationales columns added in slice 2)
# + QuestionOutcomeTag + QuizItem on the run's DRAFT topic_mastery QuizVersion.
# Question.subtopic_id = node.accepted_subtopic_id. Never RELEASED here.


# generation/lesson.py
def write_topic_lesson(*, objectives: Sequence[str], chunks: Sequence[str]) -> str:
    """One markdown document; extract Mermaid → parse → retry on parser error.
    Store on runs.draft_lesson_markdown. Do not write source_material_versions.
    """
    raise NotImplementedError
```

Publish (slice 4) is one service method: copy markdown onto new/next topic `slug=lesson` version as `published`; set quiz version `released` + open `QuizRelease`; bind with `QuizMaterialBinding`; stamp run FKs; phase `published`. Previous published topic lesson (if a later run) is `superseded`. Seeded **subtopic** lessons are left alone.

---

## Module map

```text
generation/                       # owns the run aggregate + HITL + later gen
  types.py                        # RunPhase, GenerationRun, Outline*, errors
  models.py                       # ContentGenerationRun, OutlineNode, GenerationJob
  outline.py                      # largest_remainder, DAG parse, match, heuristic
  service.py                      # submit / get / list / patch / accept (+ later publish)
  worker.py                       # on_intake_indexed, claim, process_generation_job
  router.py                       # thin HTTP + deprecated POST alias + 410 on old GET
  schemas.py                      # Pydantic outs; from_domain adapters
  items.py                        # slice 2
  lesson.py                       # slice 3

proposals/                        # DELETE. Types, generate.complete_from_chunks, router gone.

rag/
  queue.py                        # queue_topic_intake_pdf sibling; admin function unchanged
  models.py                       # IngestTargetKind UNCHANGED

workers/
  ingest.py                       # READY then on_intake_indexed; fail_run_for_intake;
                                  # delete complete_from_chunks branch; topic XOR institution join
  runner.py                       # poll ingest first, then generation_jobs

materials/
  models.py                       # topic_id XOR subtopic_id; drop in-flight proposal unique
  queries.py                      # published_topic_material_version (slice 4)

academics/
  directory.py                    # unlock branch for published generation runs (slice 4)
  models.py                       # Subtopic unchanged (no parent_subtopic_id in slice 1)

assessments/
  models.py                       # slice 2: rationale columns on question_answer_keys

db/models.py                      # import generation.models

frontend/                         # slice 5
  api/generation.ts
  pages/teacher/GenerationRunsPage.tsx
```

Call chain for slice-1 operations (≤3 files each):

- Submit: `router` → `generation.service.submit_pdf` → `rag.queue.queue_topic_intake_pdf`
- Index: `workers.ingest` → `_process_source_material` → `generation.worker.on_intake_indexed`
- Outline: `workers.runner` → `generation.worker.process_generation_job_sync` → `outline.write_outline`
- Patch / accept: `router` → `generation.service` → `outline.largest_remainder` / academics inserts

---

## Invariants encoded in types vs checked at the boundary

Encoded:

- `ItemCount` cannot be outside 60–80.
- `outline_review` cannot exist without nodes.
- `published` cannot exist without both student FKs.
- `force_create` XOR `matched_subtopic_id` on a node.
- Run phase is the only caller-facing status.
- Partial unique: one in-flight run per topic.
- Partial unique: one in-flight outline job per run.
- `source_materials` XOR parent, like quizzes.
- Quota preview is derived from weights until accept freezes integers (single source of truth).

Boundary (`_authorised_topic`, same pattern as authoring `_authorised_subtopic`):

- Institution match.
- `scope.unrestricted or offering_id in scope.taught_offering_ids`.
- Topic exists.
- Run belongs to that topic (a knowledge-doc id is 404).
- PATCH node ids belong to the run; `assert_dag`.
- `matched_subtopic_id` on PATCH belongs to the same topic.

Deliberately not done:

- No LangGraph, Redis, Kafka, MinIO, OpenSearch, second generative process.
- No `IngestTargetKind` value for runs or drafts.
- No stretching SMV `awaiting_approval` / slug `"lesson"` as the workflow.
- No `Subtopic` inserts before accept; no `parent_subtopic_id` in slice 1.
- No auto-publish. Worker never writes `published` / `released`.
- No `subtopic_mastery` quizzes from this pipeline.
- No analytics UI (tags make later insights possible).
- No generate HTTP. Accept is the resume.
- No section-scoped materials. No new grant types.
- Student quiz GET still does not join answer keys.
- Dual-role users still resolve as unrestricted admins (`scope_for` unchanged).

---

## Pseudocode for load-bearing paths

### `submit_pdf`

```python
async def submit_pdf(...):
    topic, offering_id = await _authorised_topic(session, scope, topic_id)
    count = ItemCount.parse(target_item_count)
    if await _in_flight_run_id(session, topic.id) is not None:
        raise GenerationError("A generation run is already in flight for this topic.", 409)

    data = await file.read()
    content_type = validate_pdf_upload(file, data)
    object_key = storage.build_object_key(
        institution_id=principal.institution_id,
        kind="source_materials",
        filename=file.filename or "material.pdf",
    )
    storage.store_bytes(object_key, data)

    try:
        async with session.begin_nested():
            run = ContentGenerationRun(
                topic_id=topic.id,
                submitted_by_user_id=principal.user_id,
                title=title.strip() or "Topic source",
                phase=RunPhase.INDEXING,
                target_item_count=count.value,
            )
            session.add(run)
            await session.flush()
            queued = await queue_topic_intake_pdf(
                session,
                topic_id=topic.id,
                title=run.title,
                data=data,
                content_type=content_type,
                object_key=object_key,
                submitted_by_user_id=principal.user_id,
            )
            run.intake_source_material_version_id = queued.version.id
    except IntegrityError as exc:
        if _in_flight_run_conflict(exc):
            raise GenerationError(
                "A generation run is already in flight for this topic.", 409
            ) from exc
        raise

    await record_event(..., entity_type="content_generation_run", entity_id=run.id)
    return AcceptedRun(run_id=run.id, topic_id=topic.id, phase=RunPhase.INDEXING)
```

### `on_intake_indexed`

```python
def on_intake_indexed(session, version_id):
    run = session.scalar(
        select(ContentGenerationRun).where(
            ContentGenerationRun.intake_source_material_version_id == version_id,
            ContentGenerationRun.phase == RunPhase.INDEXING,
        )
    )
    if run is None:
        return
    run.phase = RunPhase.OUTLINING
    session.add(
        GenerationJob(run_id=run.id, kind=GenerationJobKind.OUTLINE, status=QUEUED)
    )
    # no commit — caller commits with version READY
```

### `_finish_outline`

```python
def _finish_outline(session, run_id, *, writer):
    run = session.get(ContentGenerationRun, run_id)
    chunks = load_chunks_ordered(session, run.intake_source_material_version_id)
    clusters = cluster_by_heading(chunks)
    if not clusters:
        _fail_run(session, run, "No section headings to outline from")
        return
    try:
        proposed = write_outline(clusters, writer=writer)
    except Exception as exc:
        _fail_run(session, run, str(exc)[:2000])
        return
    existing = list_subtopics_for_topic(session, run.topic_id)
    matches = match_existing_subtopics(proposed, existing)
    weights = [
        combined_weight(
            token_mass=n.token_mass,
            prerequisite_score=n.prerequisite_score,
            centrality=n.centrality,
        )
        for n in proposed.nodes
    ]
    # persist OutlineNode rows with matches; quota left NULL (preview on GET)
    run.phase = RunPhase.OUTLINE_REVIEW
    run.failure_reason = None
```

### `accept_outline`

```python
async def accept_outline(...):
    run = await get_run(session, scope, run_id)
    if run.phase in {RunPhase.GENERATING, RunPhase.QA_REVIEW, RunPhase.PUBLISHED}:
        return run  # idempotent
    if run.phase is not RunPhase.OUTLINE_REVIEW:
        raise GenerationError("Only an outline waiting for review can be accepted.", 409)
    if not run.outline or not run.outline.nodes:
        raise GenerationError("Cannot accept an empty outline.", 409)

    quotas = largest_remainder(
        run.outline.normalized_weights(), run.target_item_count.value
    )
    # TODO: for each node in sequence order:
    #   if force_create or matched_subtopic_id is None:
    #       create Subtopic(slug disambiguated, sequence = max+1)
    #   else:
    #       use matched row (must belong to topic); do not rewrite its sequence/name
    #   insert LearningOutcome stubs (skip existing statements)
    #   node.quota = quotas[i]; node.accepted_subtopic_id = subtopic.id
    row.phase = RunPhase.GENERATING
    # slice 2: session.add(GenerationJob(kind=ITEMS)); session.add(... LESSON)
    await record_event(..., entity_type="content_generation_run", entity_id=run.id)
    return await get_run(session, scope, run_id)
```

### Worker institution resolve (ingest.py)

```python
# TODO: if material.topic_id is not None:
#   Topic → GradeSubjectOffering → PeriodGrade → AcademicPeriod.institution_id
# else: existing Subtopic join.
# required_roles = ["teacher", "administrator"] if material.topic_id else
#   (teacher+admin if submitted_by else student+teacher+admin)
```

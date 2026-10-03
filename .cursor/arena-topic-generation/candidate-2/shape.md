# Shape

Data structures first. Public callers import the snapshot and the service operations in `usage.md`. Persistence is the **curriculum graph** plus topic-scoped `SourceMaterialVersion` rows. There is no `content_generation_runs` aggregate. The type sketch is derived from that usage; if they disagree, change the types.

## Data structures

### Topic-scoped materials (XOR)

`source_materials` today requires `subtopic_id`. Mirror quizzes:

```text
(topic_id IS NOT NULL AND subtopic_id IS NULL)
  OR (topic_id IS NULL AND subtopic_id IS NOT NULL)
```

Partial unique `(parent, slug)` for each parent kind.

| Hangar                         | Parent     | Slug     | Student-visible when                          |
| ------------------------------ | ---------- | -------- | --------------------------------------------- |
| Teacher intake PDF             | topic      | `source` | never (READY = indexed, unpublished)          |
| Generated study lesson         | topic      | `lesson` | `lifecycle_status=published` ∧ markdown       |
| Admin / seeded leaf materials  | subtopic   | `lesson` | unchanged                                     |

`open_intake_version_id` and `target_item_count` live on the **topic `source` hangar**, not on a run and not on `topics`.

```text
source_materials.open_intake_version_id  → source_material_versions.id | NULL
source_materials.target_item_count       → 60–80, default 80, NULL on non-source rows
```

Submit compare-and-sets `open_intake_version_id` from NULL. That is in-flight uniqueness for the whole workflow (index through QA). `READY` does not drop the lock. Publish, discard (pre-accept), and abandon (post-accept) set it back to NULL.

Check: `open_intake_version_id IS NULL OR slug = 'source'`. Check: `target_item_count IS NULL OR (target_item_count BETWEEN 60 AND 80)`.

### Intake version vs lesson version

Teacher intake (`source`, submitter set):

```text
PROCESSING → READY | FAILED
```

Never `published`, never `awaiting_approval`, never markdown. Chunks: `required_roles` teacher+admin until a later student-index decision.

Topic lesson (`lesson`, created on outline accept):

```text
DRAFT (empty) → PROCESSING (writer) → DRAFT (markdown, HITL 2)
              → FAILED
              → PUBLISHED (teacher publish only)
              → ARCHIVED (abandon)
```

`READY` stays the admin index badge. Do not park QA on `awaiting_approval` (that status still requires markdown and still occupies the old proposal unique — this flow does not use it).

Provenance, not a run: `source_material_versions.generated_from_version_id` on the lesson version points at the intake version. Same column on `question_versions` for the item bank.

### Draft curriculum (HITL 1)

The teacher edits **rows that want to become the topic tree**. Live `Subtopic` uniqueness (`topic_id, slug` / `topic_id, sequence`) stays strict for student/diagnostic identity. Drafts are a sibling so a discarded outline cannot collide with seeded subtopics.

```text
subtopic_revisions
  topic_id
  source_material_version_id     -- intake PDF; generation identity
  parent_revision_id             -- draft DAG only; live Subtopic stays flat
  matched_subtopic_id            -- hybrid match; NULL ⇒ create_on_accept
  title, slug, sequence
  token_mass, prerequisite_score, centrality
  importance_weight              -- normalized in the batch
  item_quota                     -- Largest Remainder vs hangar.target_item_count
  status                         -- proposed | live | discarded

learning_outcome_revisions
  subtopic_revision_id
  statement, code, sequence
  matched_outcome_id
  status                         -- proposed | live | discarded
```

Weights and quotas stay on these rows. Live `Subtopic` does not grow generation columns. Item generation (slice 2) reads `status='live'` revisions for the open intake version.

Accept is “promote draft subtopics”: match slug/name or create; insert `LearningOutcome` stubs; set revision `status='live'` and freeze `matched_subtopic_id`; find-or-create topic `lesson` hangar with an empty DRAFT version (`generated_from_version_id=intake`). Slice 1 does not enqueue ITEMS/LESSON yet.

Discard before accept: those rows → `discarded`. No `Subtopic` insert. Lock cleared.

### Jobs keyed by version id

```text
ingest_jobs.phase = index | outline | items | lesson   -- default index
ingest_jobs.target_kind = source_material_version | knowledge_document_version
ingest_jobs.target_id   = the SMV id
```

No new `IngestTargetKind`. INDEX and OUTLINE and ITEMS target the **intake** version. LESSON targets the **lesson** version (the worker may also accept the intake id and resolve the unpublished lesson via `generated_from_version_id` — pick one in implementation and keep it; sketch: LESSON `target_id` is the lesson SMV, enqueue happens from `accept_outline` / slice 3).

### Derived phase (not stored)

`TopicGenerationPhase` is computed from lock + versions + revision statuses + latest jobs. Nothing PATCHes a phase column.

```text
lock NULL, no published topic lesson     → idle
lock NULL, published topic lesson        → published   (historical; GET still useful)
intake PROCESSING                        → indexing
INDEX succeeded, no proposed rows yet,
  or OUTLINE job queued/running          → outlining
proposed revisions exist                 → outline_review
live revisions, unpublished lesson,
  ITEMS/LESSON not both succeeded        → generating
lesson DRAFT with markdown,
  items present, both jobs succeeded     → qa_review
lock held, current-phase job FAILED      → failed
```

Single source of truth: the rows. Phase is a function, per derive-instead-of-sync.

## Load-bearing decisions

1. **The topic is the caller id.** HTTP has no `/generation-runs/{id}`. History is intake versions.
2. **Mutex on the `source` hangar**, not a partial unique on `processing|awaiting_approval`. That unique is the v1 proposal lock and is the wrong span (READY would drop it).
3. **HITL 1 is curriculum.** Outline JSON on a run would be a second tree that must be synced into `Subtopic` later. Here the draft sibling *is* the tree; accept is promotion.
4. **Intake `READY` is index-only** even for teachers. Review state is “proposed revisions exist” and “unpublished lesson markdown exists.”
5. **Worker phases, not a pipeline target kind.** `target_kind` remains “which table `target_id` points at.”
6. **Accept commits curriculum.** Abandon does not delete live subtopics. Discard is only valid while revisions are `proposed`.
7. **`Question.subtopic_id` + outcome tags on every generated item.** This pipeline never emits `subtopic_mastery` quizzes. Publish releases one `topic_mastery` quiz bound to the topic lesson.
8. **In-flight teacher work does not block admin index** on a subtopic leaf: different hangars (topic `source` vs subtopic `lesson`).

## Invariants encoded in types / schema

- XOR parent on `source_materials`.
- One open intake FK per `source` hangar (the column itself).
- CAS: `UPDATE source_materials SET open_intake_version_id=:v WHERE id=:id AND open_intake_version_id IS NULL` — 0 rows ⇒ 409.
- One PROCESSING version per `source_material_id` (keep / narrow the existing partial unique to `processing` only; drop this flow’s dependence on `awaiting_approval`).
- `awaiting_approval` still requires markdown if the enum value remains for leftover v1 rows; new code never writes it.
- Revision `proposed` rows always reference the lock’s intake version (service-enforced; optional check via join).
- Student reads: published ∧ markdown / released only. Worker has no publish path.
- Answer keys never on student query paths; rationales on `question_answer_keys`.

Validation at the service boundary (PDF, 60–80, taught offering, phase gates). Inside the module, trust the domain objects.

## What this module deliberately does not do

- No `content_generation_runs`, `generation_jobs`, or LangGraph checkpointer.
- No MinIO / Redis / Kafka / second generative service.
- No analytics UI (tagging makes it possible).
- No `parent_subtopic_id` on live `subtopics` in slice 1 (DAG lives on revisions).
- No auto-create `Subtopic` before accept.
- No stretching intake SMV into an outline/item-bank state machine (`READY`+markdown as review, `awaiting_approval` as HITL 1).
- No student-visibility switch besides existing published/released.

## Interface depth

Public surface (what HTTP and the teacher page call):

`submit_source_pdf`, `generation_snapshot`, `patch_outline`, `accept_outline`, `discard_outline`, `retry_failed_phase`, `reopen_intake`, `abandon_generation`, `qa_snapshot`, `reject_items`, `publish_topic_generation`.

That list is the workflow. Callers do not coordinate index then outline then lock then match-or-create. The service owns mutex CAS, derived phase, Largest Remainder, hybrid match, job enqueue, and “which artifact to fail.”

Wire types (`GenerationOut`, multipart forms) stop at the router. ORM (`SubtopicRevision`, `IngestJob`) stays private. per boundary-discipline, encode-lessons-in-structure, laziness-protocol: one module, short chain (router → service → jobs/outline pures).

Slice 1 exposes submit, snapshot, patch, accept, discard, retry. The rest exist as `not implemented` so the surface does not grow a fake run id later.

## Module map

Replace unreleased `modules/proposals/` (LessonProposal / `complete_from_chunks`).

```text
modules/topic_generation/
  types.py      domain snapshot, phase, errors
  service.py    public operations (deep)
  outline.py    pure: headings → DAG, largest_remainder, weight normalize
  jobs.py       INDEX follow-on, OUTLINE / ITEMS / LESSON handlers
  schemas.py    wire (router only)
  router.py     thin HTTP

modules/rag/queue.py
  queue_source_material_pdf          admin subtopic (unchanged)
  queue_topic_source_pdf             topic XOR, slug source, CAS lock, phase=index

modules/materials/queries.py
  published_topic_material_version   parallel to published_material_version

workers/ingest.py
  dispatch on job.phase; INDEX must not call complete_from_chunks
```

`authoring` stays the question-bank draft helper. This pipeline writes DRAFT questions in `jobs.write_items` using the same tables, not a second visibility model.

## Domain types

```python
# modules/topic_generation/types.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from education_platform.core.errors import DomainError


class TopicGenerationPhase(str, Enum):
    IDLE = "idle"
    INDEXING = "indexing"
    OUTLINING = "outlining"
    OUTLINE_REVIEW = "outline_review"
    GENERATING = "generating"
    QA_REVIEW = "qa_review"
    FAILED = "failed"
    PUBLISHED = "published"


class OutlineNodeAction(str, Enum):
    KEEP = "keep"
    DROP = "drop"
    MATCH = "match"  # retarget matched_subtopic_id
    CREATE = "create"


@dataclass(frozen=True, slots=True)
class OutlineOutcome:
    id: UUID
    statement: str
    code: str
    sequence: int


@dataclass(frozen=True, slots=True)
class OutlineNode:
    """Caller-facing draft subtopic. id is subtopic_revisions.id."""

    id: UUID
    title: str
    slug: str
    parent_id: UUID | None
    sequence: int
    importance_weight: Decimal
    item_quota: int
    matched_subtopic_id: UUID | None
    create_on_accept: bool
    token_mass: int
    outcomes: tuple[OutlineOutcome, ...]


@dataclass(frozen=True, slots=True)
class LessonDraft:
    version_id: UUID
    title: str
    markdown: str | None
    mermaid_ok: bool


@dataclass(frozen=True, slots=True)
class ItemBankSummary:
    target_count: int
    draft_count: int
    rejected_count: int
    by_subtopic: tuple[tuple[UUID, int, int], ...]  # subtopic_id, quota, have


@dataclass(frozen=True, slots=True)
class TopicGenerationSnapshot:
    topic_id: UUID
    phase: TopicGenerationPhase
    intake_version_id: UUID | None
    target_item_count: int
    failure_reason: str | None
    submitted_by_user_id: UUID | None
    created_at: datetime | None
    outline: tuple[OutlineNode, ...]
    lesson: LessonDraft | None
    items: ItemBankSummary | None

    def __post_init__(self) -> None:
        if self.phase is TopicGenerationPhase.IDLE:
            if self.intake_version_id is not None:
                raise ValueError("idle snapshot has no open intake")
            return
        if self.phase is TopicGenerationPhase.PUBLISHED:
            return
        if self.intake_version_id is None:
            raise ValueError("an open generation snapshot needs an intake version")
        if self.phase is TopicGenerationPhase.FAILED and not self.failure_reason:
            raise ValueError("failed snapshot needs failure_reason")
        if self.phase is TopicGenerationPhase.OUTLINE_REVIEW and not self.outline:
            raise ValueError("outline_review needs outline nodes")


@dataclass(frozen=True, slots=True)
class OutlinePatch:
    target_item_count: int | None
    nodes: tuple[OutlineNodePatch, ...]


@dataclass(frozen=True, slots=True)
class OutlineNodePatch:
    id: UUID
    action: OutlineNodeAction
    title: str | None
    slug: str | None
    parent_id: UUID | None
    importance_weight: Decimal | None
    matched_subtopic_id: UUID | None


@dataclass(frozen=True, slots=True)
class HeadingMass:
    heading: str
    token_mass: int


class TopicGenerationError(DomainError):
    """Safe to show a teacher."""

    def __init__(self, detail: str, *, status_code: int = 403) -> None:
        super().__init__(detail, status_code=status_code)
```

## Persistence sketch (Alembic, slice 1+)

```python
# extras on existing tables — not implemented, migration owns the SQL

class SourceMaterial:
    # existing +
    topic_id: UUID | None
    subtopic_id: UUID | None  # now nullable
    open_intake_version_id: UUID | None
    target_item_count: int | None
    # ck XOR; partial uq (topic_id, slug); partial uq (subtopic_id, slug)
    # ck open_intake only when slug == 'source'


class SourceMaterialVersion:
    generated_from_version_id: UUID | None  # lesson → intake


class IngestJob:
    phase: IngestJobPhase  # default INDEX


class SubtopicRevision:
    topic_id: UUID
    source_material_version_id: UUID
    parent_revision_id: UUID | None
    matched_subtopic_id: UUID | None
    title: str
    slug: str
    sequence: int
    token_mass: int
    prerequisite_score: Decimal
    centrality: Decimal
    importance_weight: Decimal
    item_quota: int
    status: str  # proposed | live | discarded


class LearningOutcomeRevision:
    subtopic_revision_id: UUID
    statement: str
    code: str
    sequence: int
    matched_outcome_id: UUID | None
    status: str


class QuestionVersion:
    generated_from_version_id: UUID | None  # slice 2


class QuestionAnswerKey:
    correct_rationale: str | None           # slice 2
    distractor_rationales: dict | None
```

## Signatures

```python
# modules/topic_generation/outline.py

def largest_remainder(weights: tuple[Decimal, ...], n: int) -> tuple[int, ...]:
    """Integer quotas that sum to n. Unit-test Alpha/Beta/Gamma 0.46, 0.33, 0.21 → 80 ⇒ 37, 26, 17."""
    raise NotImplementedError


def normalize_weights(raw: tuple[Decimal, ...]) -> tuple[Decimal, ...]:
    raise NotImplementedError


def outline_from_headings(
    headings: tuple[HeadingMass, ...],
    *,
    existing_subtopics: tuple[tuple[UUID, str, str], ...],  # id, slug, name
    target_item_count: int,
) -> tuple[OutlineNode, ...]:
    # TODO: consolidate/expand via LLM; slug-match existing; Largest Remainder quotas
    # TODO: 1–3 outcome statements per node
    raise NotImplementedError


def apply_outline_patch(
    nodes: tuple[OutlineNode, ...],
    patch: OutlinePatch,
    target_item_count: int,
) -> tuple[OutlineNode, ...]:
    """Pure. Recompute quotas after weight edits. DROP removes from the returned tuple."""
    raise NotImplementedError


def derive_phase(facts: GenerationFacts) -> TopicGenerationPhase:
    """Single place that maps lock/jobs/revisions/versions → phase. See data-structures section."""
    raise NotImplementedError


# modules/topic_generation/service.py

async def submit_source_pdf(
    session: AsyncSession,
    scope: Scope,
    principal: Principal,
    *,
    topic_id: UUID,
    title: str,
    file: UploadFile,
    target_item_count: int = 80,
) -> TopicGenerationSnapshot:
    """CAS lock on topic `source` hangar; store blob; INDEX job; 409 if lock held."""
    raise NotImplementedError


async def generation_snapshot(
    session: AsyncSession,
    scope: Scope,
    topic_id: UUID,
) -> TopicGenerationSnapshot:
    raise NotImplementedError


async def patch_outline(
    session: AsyncSession,
    scope: Scope,
    topic_id: UUID,
    patch: OutlinePatch,
) -> TopicGenerationSnapshot:
    """Requires derived phase outline_review. Writes subtopic_revisions in place."""
    raise NotImplementedError


async def accept_outline(
    session: AsyncSession,
    scope: Scope,
    topic_id: UUID,
) -> TopicGenerationSnapshot:
    """Promote proposed → live Subtopic/LearningOutcome; create empty topic lesson DRAFT.
    Slice 1: do not enqueue ITEMS/LESSON.
    Slice 2+: enqueue those jobs against the intake / lesson version ids.
    """
    raise NotImplementedError


async def discard_outline(
    session: AsyncSession,
    scope: Scope,
    topic_id: UUID,
) -> TopicGenerationSnapshot:
    """proposed → discarded; clear lock; intake stays READY or FAILED. Idempotent if already idle."""
    raise NotImplementedError


async def retry_failed_phase(
    session: AsyncSession,
    scope: Scope,
    topic_id: UUID,
) -> TopicGenerationSnapshot:
    """Re-enqueue the failed job for the same version id. No-op / 409 if phase is not failed."""
    raise NotImplementedError


async def reopen_intake(
    session: AsyncSession,
    scope: Scope,
    topic_id: UUID,
    intake_version_id: UUID,
) -> TopicGenerationSnapshot:
    """Idle topic, teacher READY source version: CAS lock, enqueue OUTLINE."""
    raise NotImplementedError


async def abandon_generation(
    session: AsyncSession,
    scope: Scope,
    topic_id: UUID,
) -> TopicGenerationSnapshot:
    """After accept, before publish. Live subtopics stay. Archive draft lesson + DRAFT items."""
    raise NotImplementedError


async def qa_snapshot(...) -> TopicGenerationSnapshot:
    raise NotImplementedError


async def reject_items(...) -> TopicGenerationSnapshot:
    raise NotImplementedError


async def publish_topic_generation(...) -> TopicGenerationSnapshot:
    """Lesson PUBLISHED; topic_mastery QuizVersion RELEASED; bind; clear lock. Never from the worker."""
    raise NotImplementedError


def submit_from_subtopic_alias(...) -> TopicGenerationSnapshot:
    """Deprecated POST .../subtopics/{id}/lesson-proposals. Resolve parent topic; same submit."""
    raise NotImplementedError


# modules/topic_generation/jobs.py

def write_outline(session: Session, intake_version_id: UUID) -> None:
    """Idempotent: replace proposed revisions for this version. Do not mark intake FAILED on LLM error.
    Set job FAILED; leave intake READY. Skip if hangar.open_intake_version_id != this version.
    """
    raise NotImplementedError


def write_items(session: Session, intake_version_id: UUID) -> None:
    """DRAFT Question + tags + keys/rationales. Provenance generated_from_version_id=intake.
    Bloom mix from revision weight. IWF retry. Do not release a quiz.
    """
    raise NotImplementedError


def write_lesson(session: Session, lesson_version_id: UUID) -> None:
    """Markdown + Mermaid parse-retry onto unpublished topic lesson. Never published."""
    raise NotImplementedError
```

## Access patterns (if these need a map, the structure is wrong)

| Pattern                                      | Walk                                              |
| -------------------------------------------- | ------------------------------------------------- |
| Is this topic busy?                          | `source` hangar `open_intake_version_id`          |
| Poll teacher UI                              | hangar + intake SMV + revisions + jobs → snapshot |
| Edit outline                                 | `subtopic_revisions` WHERE intake ∧ proposed      |
| Accept                                       | revisions → Subtopic / LearningOutcome            |
| Generate items                               | live revisions for intake → Question DRAFT        |
| Student lesson                               | published topic `lesson` version                  |
| Student quiz                                 | released `topic_mastery` for `topic_id`           |
| Discard outline                              | revisions discarded; FK null                      |
| Failed outline                               | OUTLINE job.error; intake READY                   |
| Past PDFs                                    | teacher versions of topic `source`                |

No later “we’ll index by run_id.” The intake version id already groups revisions, jobs, lesson provenance, and questions.

## Student catalog (slice 4, specified now)

`published_topic_material_version(session, topic_id)`: max published version under topic slug `lesson`.

Directory: if that row exists, unlock `topic_mastery` (published lesson, not pass-all-subtopic-quizzes). Seeded topics without a published topic lesson keep the old gate. This pipeline does not write `subtopic_mastery` quizzes; seeded leaf quizzes remain where they already exist.

## Idempotency

- Submit while lock held → 409 (not a second tree).
- Outline job twice → replace proposed rows for that intake; same snapshot.
- Accept twice → if revisions already `live` and lesson DRAFT exists, return snapshot (no-op).
- Discard twice → idle snapshot.
- Publish twice → no-op on already published lesson / released quiz.
- Retry when not `failed` → 409.
- Worker crash mid-outline → retry replaces `proposed` for that version.

## Slice 1 vs later (same shape)

Slice 1 after this sketch: XOR + hangar lock + `subtopic_revisions` + INDEX then OUTLINE + PATCH/accept/discard/retry. `accept_outline` promotes curriculum and creates the empty lesson DRAFT; it does not enqueue ITEMS/LESSON. Tests in `usage.md` terms: 202 indexing; fake outline → GET tree; PATCH weights; accept creates/matches subtopics; second submit 409; discard clears lock with no new live subtopics; student seeded lessons unchanged; admin PDF still READY + null submitter; `complete_from_chunks` gone.

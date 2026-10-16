# Shape — per-teacher overlay on a read-only base

Usage is the spec: [usage.md](usage.md). This file is derived from those call sites. Persistence stays in `generation.models`; caller types stay in `generation.types`. HTTP adapters stay in `generation.schemas` / `generation.router` and are not imported by the worker.

`not implemented` bodies are the contract. Fill-in must not revive teacher `patch_outline`.

## Module map

```
generation/                      # aggregate: GenerationRun + current base + overlays
  types.py                       # extend: rounds, overlay body, merge, review board
  models.py                      # ORM for rounds, overlays, proposed merges, lesson sections, revision asks
  overlay.py                     # pure: fingerprint, diff(overlay, base), apply merge → new document
  review.py                      # pure+session: roster, timeout/abstain, round cap, visibility
  collate.py                     # LLM writer → ProposedMerge; does not write the DAG
  service.py                     # public: auth, persistence, enqueue; the deep HTTP module
  worker.py                      # claim outline/items/lesson/collate; open_stage; never publish
  router.py                      # thin HTTP
  schemas.py                     # wire adapters only

assistant/
  strategy.py                    # AssistantGraph protocol (policy | generation_review)
  graph.py                       # existing policy graph — unchanged callers
  graphs/generation_review.py    # inject → validate → run-scoped retrieve → suggest overlay ops
  tools/retrieve_run_chunks.py   # intake SMV of this run only; not handbook retrieve_chunks
```

Do not add `OverlayService` / `ReviewService` facades that forward the same arguments. `service.py` is the public surface; `overlay.py` and `review.py` are internals. Do not split `round1.py` / `round2.py` / `qa_round.py` (temporal decomposition of one machine).

`assistant.service` keeps listing `/chats` as admin policy conversations. Generation review chat rows live on the run (generation-owned), dispatched through the strategy protocol. Both graphs call `core.llm`. Policy retrieval mix stays out of teacher review.

## Invariants encoded in types

- `TeacherRoundIndex.value in (1, 2)` — no round 3.
- `ReviewStage` selects overlay body (`OutlineOverlayBody` vs `QaOverlayBody`); a QA body cannot be saved on an outline round.
- `Approve` cannot carry ops; `RequestChanges` must carry at least one op or comment; `Abstain` is empty ops (explicit or timeout).
- `NodeAdd` has `local_key: OverlayLocalKey`, never a caller-supplied outline UUID.
- `Published` runs reject overlay writes (`PublishLock.LOCKED`).
- `GenerationRun.phase is outline_review | qa_review` is the only time an `Open` round exists.
- Fingerprint mismatch → 409, not a silent write on a stale base.
- Effective stance is derived: pending + `now >= due_at` → `ABSTAIN`. Do not store a second source of truth.

Validate at the service boundary (`put_overlay`, `submit_review`, `apply_merge`). Trust these types inside `overlay.py` / `review.py`.

## Core types

```python
# generation/types.py — additions. Existing RunPhase, OutlineDocument, OutlineNode,
# GenerationRun, ItemCount, QaItem, GenerationJobKind stay.

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID


class ReviewStage(StrEnum):
    OUTLINE = "outline"
    QA = "qa"


class TeacherRoundIndex:
    """1 or 2. successor() is None on 2 — that is the cap."""

    value: Literal[1, 2]

    def __init__(self, value: int) -> None:
        if value not in (1, 2):
            raise ValueError("teacher rounds are 1 or 2")
        self.value = value  # type: ignore[assignment]

    def successor(self) -> TeacherRoundIndex | None:
        return TeacherRoundIndex(2) if self.value == 1 else None


class RoundState(StrEnum):
    OPEN = "open"
    SEALED = "sealed"  # timed out, admin seal, or every roster member submitted
    MERGED = "merged"  # apply_merge wrote the base; successor may open


class TeacherStance(StrEnum):
    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"
    ABSTAIN = "abstain"


class OverlayOpKind(StrEnum):
    EDIT = "edit"
    DROP = "drop"
    ADD = "add"
    COMMENT = "comment"
    REJECT = "reject"  # QA items only


class PublishLock(StrEnum):
    OPEN = "open"      # in-flight run
    LOCKED = "locked"  # phase=published; overlays illegal; new run is admin submit_pdf


@dataclass(frozen=True, slots=True)
class OverlayLocalKey:
    """Teacher-scoped key for a proposed new node. Not an outline node id."""

    value: str

    def __post_init__(self) -> None:
        if not self.value.strip() or len(self.value) > 64:
            raise ValueError("local_key must be 1–64 chars")


@dataclass(frozen=True, slots=True)
class BaseFingerprint:
    """Hash of the read-only base at round open. Callers echo it; they do not invent it."""

    value: str


@dataclass(frozen=True, slots=True)
class AnchoredComment:
    node_id: UUID | None
    question_id: UUID | None
    body: str

    def __post_init__(self) -> None:
        if not self.body.strip():
            raise ValueError("comment body must be non-empty")
        if self.node_id is None and self.question_id is None:
            raise ValueError("comment must anchor to a node or item, or use OverlayBody.general_comments")


@dataclass(frozen=True, slots=True)
class NodeEditOp:
    kind: Literal[OverlayOpKind.EDIT]
    node_id: UUID  # must exist on the base
    parent_id: UUID | None
    slug: str | None
    title: str | None
    weight: object | None  # Decimal | None
    matched_subtopic_id: UUID | None
    force_create: bool | None
    proposed_outcomes: tuple[str, ...] | None
    sequence: int | None


@dataclass(frozen=True, slots=True)
class NodeDropOp:
    kind: Literal[OverlayOpKind.DROP]
    node_id: UUID


@dataclass(frozen=True, slots=True)
class NodeAddOp:
    kind: Literal[OverlayOpKind.ADD]
    local_key: OverlayLocalKey
    parent_id: UUID | None  # existing base id
    parent_local_key: OverlayLocalKey | None  # another ADD in this overlay
    slug: str
    title: str
    weight: object  # Decimal
    proposed_outcomes: tuple[str, ...]
    sequence: int

    def __post_init__(self) -> None:
        if self.parent_id is not None and self.parent_local_key is not None:
            raise ValueError("ADD parent is either a base id or a local_key")


@dataclass(frozen=True, slots=True)
class NodeCommentOp:
    kind: Literal[OverlayOpKind.COMMENT]
    node_id: UUID
    body: str


OutlineNodeOp = NodeEditOp | NodeDropOp | NodeAddOp | NodeCommentOp


@dataclass(frozen=True, slots=True)
class OutlineOverlayBody:
    stage: Literal[ReviewStage.OUTLINE]
    target_item_count: ItemCount | None
    node_ops: tuple[OutlineNodeOp, ...]
    general_comments: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SectionCommentOp:
    kind: Literal[OverlayOpKind.COMMENT]
    node_id: UUID  # lesson section == accepted outline node
    body: str


@dataclass(frozen=True, slots=True)
class SectionEditOp:
    kind: Literal[OverlayOpKind.EDIT]
    node_id: UUID
    markdown: str  # suggested replacement for that section body


@dataclass(frozen=True, slots=True)
class ItemRejectOp:
    kind: Literal[OverlayOpKind.REJECT]
    question_id: UUID
    body: str


@dataclass(frozen=True, slots=True)
class ItemCommentOp:
    kind: Literal[OverlayOpKind.COMMENT]
    question_id: UUID
    body: str


QaOp = SectionCommentOp | SectionEditOp | ItemRejectOp | ItemCommentOp


@dataclass(frozen=True, slots=True)
class QaOverlayBody:
    stage: Literal[ReviewStage.QA]
    section_ops: tuple[SectionCommentOp | SectionEditOp, ...]
    item_ops: tuple[ItemRejectOp | ItemCommentOp, ...]
    general_comments: tuple[str, ...]


OverlayBody = OutlineOverlayBody | QaOverlayBody


@dataclass(frozen=True, slots=True)
class OverlayDraft:
    base_fingerprint: BaseFingerprint
    body: OverlayBody


@dataclass(frozen=True, slots=True)
class TeacherOverlay:
    round_id: UUID
    teacher_user_id: UUID
    body: OverlayBody
    updated_at: datetime
    submitted_at: datetime | None
    submitted_stance: TeacherStance | None  # None ⇒ draft

    def is_draft(self) -> bool:
        return self.submitted_at is None


@dataclass(frozen=True, slots=True)
class DiffOp:
    """Derived. Never persisted as the write model."""

    teacher_user_id: UUID
    kind: OverlayOpKind
    node_id: UUID | None
    question_id: UUID | None
    local_key: OverlayLocalKey | None
    summary: str
    before: str | None
    after: str | None


@dataclass(frozen=True, slots=True)
class TeacherDiff:
    teacher_user_id: UUID
    stance: TeacherStance
    base_fingerprint: BaseFingerprint
    ops: tuple[DiffOp, ...]


@dataclass(frozen=True, slots=True)
class ReviewRoster:
    teacher_user_ids: frozenset[UUID]

    def __post_init__(self) -> None:
        if not self.teacher_user_ids:
            raise ValueError("a review round needs at least one assigned teacher")


@dataclass(frozen=True, slots=True)
class RosterProgress:
    size: int
    submitted: int
    abstained: int
    pending: int


@dataclass(frozen=True, slots=True)
class ReviewRound:
    id: UUID
    run_id: UUID
    stage: ReviewStage
    index: TeacherRoundIndex
    state: RoundState
    base_fingerprint: BaseFingerprint
    opened_at: datetime
    due_at: datetime
    sealed_at: datetime | None
    roster: ReviewRoster


@dataclass(frozen=True, slots=True)
class MergeNewNode:
    local_key: OverlayLocalKey
    parent_id: UUID | None
    parent_local_key: OverlayLocalKey | None
    slug: str
    title: str
    weight: object
    proposed_outcomes: tuple[str, ...]
    sequence: int


@dataclass(frozen=True, slots=True)
class ProposedMerge:
    """Admin-facing document. apply_merge is the only shared-DAG write."""

    base_fingerprint: BaseFingerprint
    target_item_count: ItemCount | None
    node_edits: tuple[NodeEditOp, ...]
    drop_ids: tuple[UUID, ...]
    new_nodes: tuple[MergeNewNode, ...]
    section_edits: tuple[SectionEditOp, ...]
    reject_question_ids: tuple[UUID, ...]
    rationale: str


@dataclass(frozen=True, slots=True)
class LessonSectionRef:
    """Written by the lesson job. QA overlays attach here. Not a student SMV."""

    outline_node_id: UUID
    sequence: int
    heading: str
    markdown: str


@dataclass(frozen=True, slots=True)
class RevisionAsk:
    id: UUID
    topic_id: UUID
    from_run_id: UUID
    teacher_user_id: UUID
    reason: str
    status: Literal["open", "honored", "dismissed"]


@dataclass(frozen=True, slots=True)
class ReviewBoard:
    stage: ReviewStage
    round: ReviewRound
    publish_lock: PublishLock
    my_overlay: TeacherOverlay | None
    my_effective_stance: TeacherStance | None  # None if still pending and not due
    visible_diffs: tuple[TeacherDiff, ...]  # sealed overlays only
    roster_progress: RosterProgress
    proposed_merge: ProposedMerge | None
    lesson_sections: tuple[LessonSectionRef, ...]  # empty before qa_review


# GenerationRun grows `review: ReviewBoard | None` (None while indexing/outlining/generating/failed).


class AssistantKind(StrEnum):
    POLICY = "policy"
    GENERATION_REVIEW = "generation_review"
```

Existing `GenerationJobKind` gains `COLLATE = "collate"` (one in-flight collate per run, same partial-unique pattern as outline/items/lesson).

## Pure functions (internals)

```python
# generation/overlay.py

def fingerprint_outline(document: OutlineDocument) -> BaseFingerprint:
    raise NotImplementedError

def fingerprint_qa(*, sections: tuple[LessonSectionRef, ...], item_ids: tuple[UUID, ...]) -> BaseFingerprint:
    raise NotImplementedError

def diff_outline(base: OutlineDocument, overlay: TeacherOverlay) -> TeacherDiff:
    raise NotImplementedError

def diff_qa(
    *,
    sections: tuple[LessonSectionRef, ...],
    overlay: TeacherOverlay,
) -> TeacherDiff:
    raise NotImplementedError

def apply_outline_merge(base: OutlineDocument, merge: ProposedMerge) -> OutlineDocument:
    """Return a new document. Minting UUIDs for MergeNewNode happens in service on persist."""
    raise NotImplementedError

def stance_holds(body: OverlayBody, stance: TeacherStance) -> None:
    """Approve ⇒ no ops; request_changes ⇒ ≥1 op/comment; abstain ⇒ no ops. Else ValueError."""
    raise NotImplementedError
```

```python
# generation/review.py

from datetime import datetime

def effective_stance(overlay: TeacherOverlay | None, round: ReviewRound, now: datetime) -> TeacherStance | None:
    """None = still pending. Timeout with no submit → ABSTAIN (even if a draft body exists)."""
    raise NotImplementedError

def visible_to(viewer_user_id: UUID, *, is_closer: bool, overlay: TeacherOverlay) -> bool:
    """Own overlay always. Others iff sealed. Closer sees sealed only, not live drafts."""
    raise NotImplementedError

def assert_can_open_successor(round: ReviewRound) -> TeacherRoundIndex:
    """Raises GenerationError 409 if index is 2 or state is not MERGED."""
    raise NotImplementedError

def progress(round: ReviewRound, overlays: tuple[TeacherOverlay, ...], now: datetime) -> RosterProgress:
    raise NotImplementedError
```

```python
# generation/collate.py

def write_proposed_merge(
    *,
    stage: ReviewStage,
    base: OutlineDocument,
    sections: tuple[LessonSectionRef, ...],
    diffs: tuple[TeacherDiff, ...],
) -> ProposedMerge:
    """One bounded LLM pass via core.llm. Heuristic concat if OpenRouter is missing."""
    raise NotImplementedError
```

## Public service signatures

Auth: `_authorised_topic` (institution + `taught_offering_ids` / unrestricted). Closer ops call `_require_closer`. Dual-role admins act as closer only — they do not file teacher overlays.

```python
# generation/service.py — new and changed. Existing submit_pdf, get_run, list_runs,
# discard_outline, retry_failed, qa_items_for_run, reject_items, publish remain.

async def get_run(session: AsyncSession, scope: Scope, run_id: UUID) -> GenerationRun:
    """Seals expired rounds lazily, then returns run.review populated when a round exists."""
    raise NotImplementedError

async def put_overlay(
    session: AsyncSession,
    scope: Scope,
    principal: Principal,
    run_id: UUID,
    draft: OverlayDraft,
) -> GenerationRun:
    """Upsert the caller's draft for the open round. 409 if fingerprint mismatch, round sealed,
    phase published, or body.stage != round.stage. Does not mutate outline nodes."""
    raise NotImplementedError

async def submit_review(
    session: AsyncSession,
    scope: Scope,
    principal: Principal,
    run_id: UUID,
    *,
    stance: TeacherStance,
    draft: OverlayDraft | None = None,
) -> GenerationRun:
    """Seal my overlay. Optional draft is the last put. Idempotent if same stance+fingerprint."""
    raise NotImplementedError

async def seal_round(
    session: AsyncSession,
    scope: Scope,
    principal: Principal,
    run_id: UUID,
) -> GenerationRun:
    """Admin. Pending roster → ABSTAIN. Draft bodies remain for closer reading after seal."""
    raise NotImplementedError

async def collate_overlays(
    session: AsyncSession,
    scope: Scope,
    principal: Principal,
    run_id: UUID,
) -> GenerationRun:
    """Admin. Enqueue kind=collate. 409 unless round is open or sealed (not merged) and stage matches."""
    raise NotImplementedError

async def apply_merge(
    session: AsyncSession,
    scope: Scope,
    principal: Principal,
    run_id: UUID,
    merge: ProposedMerge,
) -> GenerationRun:
    """Admin. The shared write: outline nodes and/or lesson section markdown + item archive.
    Mints node UUIDs. Seals round as MERGED. Opens successor if index is 1; else closer must
    accept_outline / publish / discard. Curriculum rows still wait for accept_outline."""
    raise NotImplementedError

async def accept_outline(
    session: AsyncSession,
    scope: Scope,
    principal: Principal,
    run_id: UUID,
) -> GenerationRun:
    """Admin closer. Seals remaining as abstain. Writes live Subtopic/LO, freezes quotas,
    enqueues items+lesson. Legal with mixed stances (override). Idempotent after generating+."""
    raise NotImplementedError

async def discard_outline(
    session: AsyncSession,
    scope: Scope,
    principal: Principal,
    run_id: UUID,
) -> GenerationRun:
    """Admin. outline_review | failed | qa_review → discarded. 409 while a worker phase owns
    the run or after publish. Overlays stay for audit; students unchanged."""
    raise NotImplementedError

async def publish(
    session: AsyncSession,
    scope: Scope,
    principal: Principal,
    run_id: UUID,
) -> PublishedTopic:
    """Admin. Seals remaining QA as abstain. Copies draft lesson + released topic_mastery.
    Sets PublishLock.LOCKED. Worker never calls this."""
    raise NotImplementedError

async def ask_revision(
    session: AsyncSession,
    scope: Scope,
    principal: Principal,
    run_id: UUID,
    *,
    reason: str,
) -> RevisionAsk:
    """Teacher, published run only. Does not unlock overlays. Admin submit_pdf honors it."""
    raise NotImplementedError

async def post_review_chat(
    session: AsyncSession,
    scope: Scope,
    principal: Principal,
    run_id: UUID,
    *,
    content: str,
) -> ReviewChatTurn:
    """Run the generation_review AssistantGraph. May return suggested OverlayDraft ops.
    Does not put_overlay. Never called from student routes; QA keys may appear here only."""
    raise NotImplementedError
```

```python
@dataclass(frozen=True, slots=True)
class ReviewChatTurn:
    assistant_content: str
    suggested_ops: OverlayBody | None
    citations: tuple[tuple[str, str], ...]  # (label, excerpt) from this run's intake
```

`patch_outline` is removed from the public service. Router returns 410.

`reject_items` remains an admin closer shortcut (same archive + `REGENERATE_ITEMS` job). `apply_merge` with `reject_question_ids` is the overlay-aware path and should share the same persist helper — not two policies.

## Assistant strategy

```python
# assistant/strategy.py

from typing import Protocol
from education_platform.modules.authorization.principal import Principal
from education_platform.modules.authorization.scope import Scope


class AssistantContext(Protocol):
    kind: AssistantKind
    generation_run_id: UUID | None


class AssistantGraph(Protocol):
    kind: AssistantKind

    def authorize(self, principal: Principal, scope: Scope, context: AssistantContext) -> None:
        raise NotImplementedError

    async def run_turn(self, session: AsyncSession, context: AssistantContext, user_message: str) -> ReviewChatTurn:
        raise NotImplementedError


def graph_for(kind: AssistantKind) -> AssistantGraph:
    raise NotImplementedError
```

- `POLICY`: today's inject → validate → `retrieve_chunks` (handbook + curriculum) → summarize. Admin `/chats` only.
- `GENERATION_REVIEW`: inject → validate (this topic/run) → `retrieve_run_chunks` (intake SMV of **this** run) → optional outline-node read → suggest overlay ops. Teaching route only. No handbook mix, no student serialization of keys.

Do not instantiate a second OpenRouter client. Do not import `assistant.graph.run_assistant_turn` from generation service; dispatch `graph_for(GENERATION_REVIEW)`.

## Persistence sketch (Alembic, not product code)

`content_generation_review_rounds`: `run_id`, `stage`, `index` (1|2 CHECK), `state`, `base_fingerprint`, `opened_at`, `due_at`, `sealed_at`, `roster` JSON. UNIQUE `(run_id, stage, index)`. Partial UNIQUE one `state='open'` row per `run_id`.

`content_generation_teacher_overlays`: `round_id`, `teacher_user_id`, `body` JSON, `submitted_at`, `submitted_stance`. UNIQUE `(round_id, teacher_user_id)`.

`content_generation_proposed_merges`: `round_id` UNIQUE, `document` JSON, `job_id` nullable.

`content_generation_lesson_sections`: `run_id`, `outline_node_id` UNIQUE, `heading`, `markdown`, `sequence`. Written by the lesson job; read-only to teachers.

`content_generation_revision_asks`: `topic_id`, `from_run_id`, `teacher_user_id`, `reason`, `status`. Partial UNIQUE one `status='open'` per `topic_id`.

`content_generation_review_chats` / `..._messages`: `run_id`, `owner_user_id`. Not `chat_conversations` (policy list stays clean).

## Data flow

1. Outline job writes `content_generation_outline_nodes`, sets `outline_review`, `open_stage(OUTLINE, 1)` with roster = active teaching assignments on the topic offering (`taught_offering_ids`).
2. Teachers `put_overlay` / `submit_review`. Shared rows unchanged. GET derives `TeacherDiff`.
3. Admin `collate` (job) and/or edits `ProposedMerge`, then `apply_merge`. That persist is the first shared mutation since the job. Round 1 → `MERGED`; round 2 opens with a new fingerprint **or** (if index was 2) closer proceeds.
4. `accept_outline` writes curriculum (not earlier). Items+lesson jobs write draft quiz + section rows + stitched markdown.
5. QA stage repeats 2–3 against `LessonSectionRef` + `QaItem`. `publish` is the student write and sets `PublishLock.LOCKED`.
6. Timeout: `get_run` / closer ops call `seal_expired`. Worker may sweep; lazy read is authoritative.

## Interface depth

Public teaching surface: `put_overlay`, `submit_review`, `post_review_chat`, `ask_revision`, plus existing get/list. Public closer surface: `collate`, `merge`, `seal_round`, plus existing accept/discard/retry/reject/publish. That is small relative to roster snapshots, privacy, fingerprints, round cap, abstain, collate, UUID minting, curriculum freeze, and graph dispatch — those stay behind `service.py`.

Exposed on purpose: `ReviewBoard` (the HITL UI), `OverlayBody` (the teacher document), `ProposedMerge` (the closer document), `RunPhase` (async poll). Not exposed: job rows, overlay ORM, fingerprint algorithm, LangGraph state, SMV lifecycle, answer keys on student routes.

## Deliberately out of scope

- Per-teacher student lessons or section-scoped generation grants.
- GitHub-style `OutlineRevision` snapshot chain as the aggregate (that is the other candidate).
- Reusing `awaiting_approval` SMV as outline review.
- Teacher PDF upload.
- Redis/Kafka/MinIO.
- Copying the policy LangGraph retrieve mix into teacher chat.
- Auto-publish when the roster is unanimous.

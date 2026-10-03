# Shape

## Domain types first

The sketches use distinct IDs for frozen revisions and stable target keys. A database row ID identifies one snapshot row; a stable key follows the same logical node, section, or item across revisions and is what comments and diffs anchor to.

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Generic, Literal, NewType, TypeVar
from uuid import UUID

OutlineRevisionId = NewType("OutlineRevisionId", UUID)
ContentRevisionId = NewType("ContentRevisionId", UUID)
ReviewRoundId = NewType("ReviewRoundId", UUID)
ReviewDecisionId = NewType("ReviewDecisionId", UUID)
ChangeRequestId = NewType("ChangeRequestId", UUID)
StableTargetKey = NewType("StableTargetKey", UUID)
SnapshotHash = NewType("SnapshotHash", str)

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class NonEmpty(Generic[T]):
    head: T
    tail: tuple[T, ...] = ()

    def as_tuple(self) -> tuple[T, ...]:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class RevisionNumber:
    value: int

    def __post_init__(self) -> None:
        """Require value >= 1."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class TeacherRoundNumber:
    value: int

    def __post_init__(self) -> None:
        """Require 1 <= value <= 2."""
        raise NotImplementedError


class RevisionOrigin(StrEnum):
    INITIAL_GENERATION = "initial_generation"
    COLLATED_REWRITE = "collated_rewrite"
    ADMIN_OVERRIDE = "admin_override"


@dataclass(frozen=True, slots=True)
class HumanActorStamp:
    user_id: UUID
    display_name: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class WorkerActorStamp:
    job_id: UUID
    model: str
    occurred_at: datetime


RevisionAuthor = HumanActorStamp | WorkerActorStamp


@dataclass(frozen=True, slots=True)
class ProposedOutcomeSnapshot:
    statement: str


@dataclass(frozen=True, slots=True)
class OutlineNodeSnapshot:
    node_key: StableTargetKey
    parent_node_key: StableTargetKey | None
    slug: str
    title: str
    token_mass: int
    prerequisite_score: Decimal
    centrality: Decimal
    weight: Decimal
    matched_subtopic_id: UUID | None
    force_create: bool
    proposed_outcomes: tuple[ProposedOutcomeSnapshot, ...]
    sequence: int


@dataclass(frozen=True, slots=True)
class OutlineSnapshot:
    target_item_count: int
    nodes: tuple[OutlineNodeSnapshot, ...]

    def __post_init__(self) -> None:
        """Validate 60..80 count, unique keys/slugs, parent closure, DAG, weights and outcomes."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class OutlineRevision:
    id: OutlineRevisionId
    run_id: UUID
    number: RevisionNumber
    parent_id: OutlineRevisionId | None
    origin: RevisionOrigin
    created_by: RevisionAuthor
    source_round_id: ReviewRoundId | None
    snapshot_hash: SnapshotHash
    snapshot: OutlineSnapshot
    created_at: datetime


@dataclass(frozen=True, slots=True)
class LessonSectionSnapshot:
    section_key: StableTargetKey
    heading: str
    markdown: str
    sequence: int


@dataclass(frozen=True, slots=True)
class QuizOptionSnapshot:
    label: str
    text: str
    sequence: int


@dataclass(frozen=True, slots=True)
class QuizAnswerKeySnapshot:
    correct_label: str
    correct_rationale: str
    distractor_rationales: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class QuizItemSnapshot:
    item_key: StableTargetKey
    question_id: UUID
    question_version_id: UUID
    subtopic_id: UUID
    prompt: str
    options: tuple[QuizOptionSnapshot, ...]
    answer_key: QuizAnswerKeySnapshot
    sequence: int


@dataclass(frozen=True, slots=True)
class ContentSnapshot:
    rendered_lesson_markdown: str
    lesson_sections: tuple[LessonSectionSnapshot, ...]
    quiz_version_id: UUID
    quiz_items: tuple[QuizItemSnapshot, ...]

    def __post_init__(self) -> None:
        """Require stable unique keys, ordered sections/items, valid keys, and rendered consistency."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class ContentRevision:
    id: ContentRevisionId
    run_id: UUID
    number: RevisionNumber
    parent_id: ContentRevisionId | None
    origin: RevisionOrigin
    created_by: RevisionAuthor
    source_round_id: ReviewRoundId | None
    snapshot_hash: SnapshotHash
    snapshot: ContentSnapshot
    created_at: datetime


FrozenRevision = OutlineRevision | ContentRevision
```

`ContentSnapshot` is a staff-only domain type. Student serializers do not import it. Unchanged quiz items may reuse immutable `QuestionVersion` rows across content revisions; rewritten items receive new versions. The snapshot still records the complete ordered quiz so a revision never depends on “latest” rows.

## Attributed reviews

Teacher decisions are append-only and actor-owned. The administrator closes a frozen round but never modifies teacher decisions. A teacher can submit once per round; editing is local UI state before submit.

```python
class ChangeKind(StrEnum):
    CURRICULUM_ALIGNMENT = "curriculum_alignment"
    FACTUAL_ACCURACY = "factual_accuracy"
    PEDAGOGY = "pedagogy"
    STRUCTURE = "structure"
    ASSESSMENT_VALIDITY = "assessment_validity"
    ANSWER_KEY = "answer_key"
    ACCESSIBILITY = "accessibility"
    OTHER = "other"


class OutlineField(StrEnum):
    WHOLE_NODE = "whole_node"
    TITLE = "title"
    PARENT = "parent"
    WEIGHT = "weight"
    PROPOSED_OUTCOMES = "proposed_outcomes"
    SUBTOPIC_MATCH = "subtopic_match"
    OUTLINE_STRUCTURE = "outline_structure"


class LessonField(StrEnum):
    WHOLE_SECTION = "whole_section"
    HEADING = "heading"
    BODY = "body"
    ORDER = "order"


class QuizField(StrEnum):
    WHOLE_ITEM = "whole_item"
    PROMPT = "prompt"
    OPTIONS = "options"
    ANSWER_KEY = "answer_key"
    RATIONALES = "rationales"
    ORDER = "order"


@dataclass(frozen=True, slots=True)
class OutlineNodeTarget:
    kind: Literal["outline_node"]
    node_key: StableTargetKey


@dataclass(frozen=True, slots=True)
class OutlineDocumentTarget:
    """Used for add/remove/reorder requests not owned by one node."""
    kind: Literal["outline_document"]


@dataclass(frozen=True, slots=True)
class LessonSectionTarget:
    kind: Literal["lesson_section"]
    section_key: StableTargetKey


@dataclass(frozen=True, slots=True)
class QuizItemTarget:
    kind: Literal["quiz_item"]
    item_key: StableTargetKey


@dataclass(frozen=True, slots=True)
class DraftOutlineRequest:
    target: OutlineNodeTarget | OutlineDocumentTarget
    field: OutlineField
    kind: ChangeKind
    comment: str


@dataclass(frozen=True, slots=True)
class DraftLessonRequest:
    target: LessonSectionTarget
    field: LessonField
    kind: ChangeKind
    comment: str


@dataclass(frozen=True, slots=True)
class DraftQuizRequest:
    target: QuizItemTarget
    field: QuizField
    kind: ChangeKind
    comment: str


DraftChangeRequest = DraftOutlineRequest | DraftLessonRequest | DraftQuizRequest


@dataclass(frozen=True, slots=True)
class SubmitApproval:
    revision_id: OutlineRevisionId | ContentRevisionId
    verdict: Literal["approve"]


@dataclass(frozen=True, slots=True)
class SubmitChangesRequested:
    revision_id: OutlineRevisionId | ContentRevisionId
    verdict: Literal["changes_requested"]
    requests: NonEmpty[DraftChangeRequest]


TeacherDecisionCommand = SubmitApproval | SubmitChangesRequested


@dataclass(frozen=True, slots=True)
class ChangeRequest:
    id: ChangeRequestId
    decision_id: ReviewDecisionId
    revision_id: OutlineRevisionId | ContentRevisionId
    author: HumanActorStamp
    request: DraftChangeRequest


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    id: ReviewDecisionId
    round_id: ReviewRoundId
    revision_id: OutlineRevisionId | ContentRevisionId
    reviewer: HumanActorStamp
    verdict: Literal["approve"]


@dataclass(frozen=True, slots=True)
class ChangesRequestedDecision:
    id: ReviewDecisionId
    round_id: ReviewRoundId
    revision_id: OutlineRevisionId | ContentRevisionId
    reviewer: HumanActorStamp
    verdict: Literal["changes_requested"]
    requests: NonEmpty[ChangeRequest]


TeacherDecision = ApprovalDecision | ChangesRequestedDecision


@dataclass(frozen=True, slots=True)
class ReviewParticipant:
    reviewer_user_id: UUID
    display_name: str
    teaching_assignment_ids: NonEmpty[UUID]


@dataclass(frozen=True, slots=True)
class ReviewRound:
    id: ReviewRoundId
    run_id: UUID
    revision_id: OutlineRevisionId | ContentRevisionId
    number: TeacherRoundNumber
    participants: tuple[ReviewParticipant, ...]
    opened_at: datetime
    closes_at: datetime


class ReviewerStateKind(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    ABSTAINED = "abstained"


@dataclass(frozen=True, slots=True)
class ReviewerState:
    participant: ReviewParticipant
    state: ReviewerStateKind
    decision: TeacherDecision | None
```

The participant roster is copied from active, offering-scoped teaching assignments when the round opens. It is evidence of who was invited, not a new access grant. Every request still rechecks the caller's current assignment. Section-specific assignments collapse to one reviewer for this topic-wide curriculum.

`pending` and `abstained` are projections, not mutable participant state. With no close record, an unanswered participant is pending before `closes_at` and abstained afterwards. When an administrator closes early, unanswered participants are abstained at the close timestamp. Silence is never converted to approval.

## Round closure and bounded rewrites

```python
@dataclass(frozen=True, slots=True)
class RewriteCurrent:
    revision_id: OutlineRevisionId | ContentRevisionId
    action: Literal["rewrite"]


@dataclass(frozen=True, slots=True)
class AcceptCurrent:
    revision_id: OutlineRevisionId | ContentRevisionId
    action: Literal["accept_current"]


@dataclass(frozen=True, slots=True)
class OverrideOutlineAndAccept:
    revision_id: OutlineRevisionId
    action: Literal["override_and_accept"]
    replacement: OutlineSnapshot
    rationale: str


@dataclass(frozen=True, slots=True)
class OverrideContentAndAccept:
    revision_id: ContentRevisionId
    action: Literal["override_and_accept"]
    replacement: ContentSnapshot
    rationale: str


@dataclass(frozen=True, slots=True)
class DiscardRun:
    revision_id: OutlineRevisionId | ContentRevisionId
    action: Literal["discard"]
    rationale: str


CloseRoundCommand = (
    RewriteCurrent
    | AcceptCurrent
    | OverrideOutlineAndAccept
    | OverrideContentAndAccept
    | DiscardRun
)


@dataclass(frozen=True, slots=True)
class RoundCloseRecord:
    id: UUID
    round_id: ReviewRoundId
    base_revision_id: OutlineRevisionId | ContentRevisionId
    action: str
    actor: HumanActorStamp
    collated_request_ids: tuple[ChangeRequestId, ...]
    rationale: str | None


@dataclass(frozen=True, slots=True)
class RewritePlan:
    close_record_id: UUID
    run_id: UUID
    base_revision_id: OutlineRevisionId | ContentRevisionId
    request_ids: NonEmpty[ChangeRequestId]
    next_revision_number: RevisionNumber
    next_teacher_round: TeacherRoundNumber
    max_model_calls: Literal[1] = 1


@dataclass(frozen=True, slots=True)
class RewriteQueued:
    kind: Literal["rewrite_queued"]
    job_id: UUID
    close_record: RoundCloseRecord


@dataclass(frozen=True, slots=True)
class OutlineAccepted:
    kind: Literal["outline_accepted"]
    run_id: UUID
    accepted_revision_id: OutlineRevisionId


@dataclass(frozen=True, slots=True)
class ContentPublished:
    kind: Literal["content_published"]
    run_id: UUID
    accepted_revision_id: ContentRevisionId
    lesson_version_id: UUID
    quiz_version_id: UUID


@dataclass(frozen=True, slots=True)
class RunDiscarded:
    kind: Literal["run_discarded"]
    run_id: UUID


CloseRoundResult = RewriteQueued | OutlineAccepted | ContentPublished | RunDiscarded
```

`rewrite` requires at least one submitted request and is legal only for teacher round 1. The close transaction freezes the exact request IDs into `RoundCloseRecord` and queues one job. The worker makes one model call, validates the candidate, preserves stable keys for unchanged targets, creates revision N+1, then opens teacher round 2. It copies untouched lesson sections and quiz items without asking the model to regenerate them. A failed rewrite remains failed; it cannot silently make another model call. The administrator can resolve it with a frozen override or discard.

After teacher round 2 there is no `TeacherRoundNumber(3)`, so `rewrite` cannot produce another teacher round. `override_and_accept` stores a complete revision N+1 with `ADMIN_OVERRIDE`, actor, timestamp, rationale, and snapshot diff, then accepts that new revision in the same administrator transaction. It is not a PATCH of the current revision.

## Diff and review-page read model

```python
@dataclass(frozen=True, slots=True)
class ValueDelta(Generic[T]):
    before: T | None
    after: T | None


@dataclass(frozen=True, slots=True)
class OutlineNodeDelta:
    node_key: StableTargetKey
    before: OutlineNodeSnapshot | None
    after: OutlineNodeSnapshot | None


@dataclass(frozen=True, slots=True)
class LessonSectionDelta:
    section_key: StableTargetKey
    before: LessonSectionSnapshot | None
    after: LessonSectionSnapshot | None


@dataclass(frozen=True, slots=True)
class QuizItemDelta:
    item_key: StableTargetKey
    before: QuizItemSnapshot | None
    after: QuizItemSnapshot | None


@dataclass(frozen=True, slots=True)
class OutlineRevisionDiff:
    kind: Literal["outline"]
    from_revision_id: OutlineRevisionId
    to_revision_id: OutlineRevisionId
    target_item_count: ValueDelta[int]
    nodes: tuple[OutlineNodeDelta, ...]


@dataclass(frozen=True, slots=True)
class ContentRevisionDiff:
    kind: Literal["content"]
    from_revision_id: ContentRevisionId
    to_revision_id: ContentRevisionId
    sections: tuple[LessonSectionDelta, ...]
    quiz_items: tuple[QuizItemDelta, ...]


RevisionDiff = OutlineRevisionDiff | ContentRevisionDiff
ReviewTargetSnapshot = (
    OutlineNodeSnapshot | OutlineSnapshot | LessonSectionSnapshot | QuizItemSnapshot
)


@dataclass(frozen=True, slots=True)
class RequestAgainstTarget:
    change_request: ChangeRequest
    target_at_reviewed_revision: ReviewTargetSnapshot


@dataclass(frozen=True, slots=True)
class ReviewWorkspace:
    run_id: UUID
    topic_id: UUID
    phase: str
    active_revision: FrozenRevision
    diff_from_parent: RevisionDiff | None
    open_round: ReviewRound | None
    reviewer_states: tuple[ReviewerState, ...]
    request_threads: tuple[RequestAgainstTarget, ...]
    history: tuple[RoundCloseRecord, ...]
    published_locked: bool
```

Revision-to-revision diffs compare stable target keys and complete snapshots, never mutable “current” rows. Request threads resolve against the revision named by the request, so later rewrites cannot change the text shown beside an old comment.

## Deep service interface

The HTTP layer needs only one read and two review commands. The service hides offering authorization, stale-revision checks, roster projection, deadlines, collation, revision insertion, curriculum materialization, job enqueueing, and administrator-only publication.

```python
# generation/review.py

async def get_review_workspace(
    session: AsyncSession,
    scope: Scope,
    principal: Principal,
    run_id: UUID,
) -> ReviewWorkspace:
    raise NotImplementedError


async def submit_teacher_decision(
    session: AsyncSession,
    scope: Scope,
    principal: Principal,
    run_id: UUID,
    round_id: ReviewRoundId,
    command: TeacherDecisionCommand,
) -> TeacherDecision:
    raise NotImplementedError


async def close_review_round(
    session: AsyncSession,
    scope: Scope,
    principal: Principal,
    run_id: UUID,
    round_id: ReviewRoundId,
    command: CloseRoundCommand,
) -> CloseRoundResult:
    raise NotImplementedError


# Worker-only entry point. It can install a draft successor, never accept or publish it.
async def complete_rewrite(
    session: AsyncSession,
    plan: RewritePlan,
    candidate: OutlineSnapshot | ContentSnapshot,
) -> FrozenRevision:
    raise NotImplementedError
```

The worker's rewrite adapter is one stage-dispatched operation, not a caller-driven sequence:

```python
# generation/rewrite.py

async def rewrite_revision_once(
    *,
    plan: RewritePlan,
    base: FrozenRevision,
    requests: NonEmpty[ChangeRequest],
    intake_evidence: tuple[RetrievedChunk, ...],
    llm: LlmGateway,
) -> OutlineSnapshot | ContentSnapshot:
    """One completion call; parse and validate the appropriate complete successor snapshot."""
    raise NotImplementedError
```

Initial outline and content generation call `install_initial_revision(...)` internally when their existing jobs succeed. This replaces run-scoped mutable outline rows and `draft_lesson_markdown` as review sources. The existing run phases remain the coarse workflow projection: `outline_review` means an outline leaf revision exists; `qa_review` means a content leaf revision exists.

## Thin HTTP signatures

```python
# generation/router.py

@router.get(
    "/teaching/generation-runs/{run_id}/review",
    response_model=ReviewWorkspaceOut,
)
async def show_review(
    run_id: UUID,
    request: ScopedRequest = Depends(scoped("teaching.generation.review.get")),
) -> ReviewWorkspaceOut:
    raise NotImplementedError


@router.post(
    "/teaching/generation-runs/{run_id}/review-rounds/{round_id}/decision",
    response_model=TeacherDecisionOut,
    status_code=status.HTTP_201_CREATED,
)
async def submit_decision(
    run_id: UUID,
    round_id: UUID,
    body: TeacherDecisionIn,
    request: ScopedRequest = Depends(scoped("teaching.generation.review.submit")),
) -> TeacherDecisionOut:
    raise NotImplementedError


@router.post(
    "/teaching/generation-runs/{run_id}/review-rounds/{round_id}/close",
    response_model=CloseRoundResultOut,
)
async def close_round(
    run_id: UUID,
    round_id: UUID,
    body: CloseRoundIn,
    request: ScopedRequest = Depends(scoped("teaching.generation.review.close")),
    _admin: Principal = Depends(require_administrator),
) -> CloseRoundResultOut:
    raise NotImplementedError
```

The existing administrator upload, teaching run show/list, discard/retry, and student material/quiz routes remain. The live outline PATCH is removed. `accept-outline`, `reject-items`, and `publish` become obsolete once the close command is adopted; during rollout they may return `410 Gone` with the replacement URL rather than forwarding into the new service.

## Assistant strategy

The LLM transport remains `core.llm`. Strategies own graph shape, authorization/context loading, and tool selection; they do not own another client.

```python
# assistant/strategy.py

@dataclass(frozen=True, slots=True)
class PolicyAssistantContext:
    kind: Literal["policy"]
    institution_id: UUID


@dataclass(frozen=True, slots=True)
class GenerationAssistantContext:
    kind: Literal["generation_review"]
    run_id: UUID
    revision_id: OutlineRevisionId | ContentRevisionId
    target: (
        OutlineNodeTarget
        | OutlineDocumentTarget
        | LessonSectionTarget
        | QuizItemTarget
        | None
    )


AssistantContext = PolicyAssistantContext | GenerationAssistantContext


@dataclass(frozen=True, slots=True)
class AssistantReply:
    content: str
    citations: tuple[ChatCitation, ...]
    draft_change_request: DraftChangeRequest | None


class AssistantStrategy(Protocol):
    async def run_turn(
        self,
        *,
        session: AsyncSession,
        principal: Principal,
        context: AssistantContext,
        history: tuple[ChatTurn, ...],
        message: str,
        llm: LlmGateway,
    ) -> AssistantReply:
        raise NotImplementedError


class AssistantStrategyRegistry:
    def for_context(self, context: AssistantContext) -> AssistantStrategy:
        raise NotImplementedError


async def run_assistant_turn(
    session: AsyncSession,
    principal: Principal,
    context: AssistantContext,
    history: tuple[ChatTurn, ...],
    message: str,
) -> AssistantReply:
    """Resolve a strategy, authorize context, and use the shared core.llm gateway."""
    raise NotImplementedError
```

`PolicyAssistantStrategy` retains the current admin handbook graph and retrieval behavior behind the unchanged `/admin/policy/chats` API. `GenerationReviewStrategy` builds a separate graph with generation-specific tools: load the named frozen revision, resolve the named target, and retrieve intake chunks already authorized for teacher/admin use. It can explain content or emit a typed draft request. It cannot submit decisions, close rounds, enqueue jobs, or publish.

```python
# generation/router.py

@router.post(
    "/teaching/generation-runs/{run_id}/assistant/turns",
    response_model=GenerationAssistantReplyOut,
)
async def generation_assistant_turn(
    run_id: UUID,
    body: GenerationAssistantTurnIn,
    request: ScopedRequest = Depends(scoped("teaching.generation.assistant")),
) -> GenerationAssistantReplyOut:
    raise NotImplementedError
```

## Frontend boundary

Transport DTOs stay in `frontend/src/api/types.ts`; UI components consume the discriminated workspace and commands, not persistence shapes.

```ts
export function getGenerationReview(runId: string): Promise<ReviewWorkspace>;

export function submitReviewDecision(
  runId: string,
  roundId: string,
  command: TeacherDecisionCommand,
): Promise<TeacherDecision>;

export function closeReviewRound(
  runId: string,
  roundId: string,
  command: CloseRoundCommand,
): Promise<CloseRoundResult>;

export function askGenerationAssistant(
  runId: string,
  command: GenerationAssistantTurn,
): Promise<GenerationAssistantReply>;
```

The review component switches exhaustively on revision stage, decision verdict, target kind, and close result. Answer-key fields exist only in teaching review DTOs.

## Persistence map and constraints

- `content_generation_runs`: keep topic, intake, phase, submitter, publish references, and the existing one-in-flight partial unique index. Published runs are locked. Do not store a mutable review document as the source of truth.
- `generation_revisions`: immutable envelope (`run_id`, stage, number, parent revision, origin, creator, source round, hash). Unique `(run_id, stage, number)` and unique non-null `parent_revision_id` enforce a linear history. One initial revision per `(run_id, stage)`.
- `generation_outline_revision_nodes`: immutable node snapshots keyed by revision, with stable `node_key` and `parent_node_key`. Unique `(revision_id, node_key)` and `(revision_id, slug)`.
- `generation_content_revisions`: immutable lesson markdown and draft quiz-version reference, one row per content revision.
- `generation_lesson_section_snapshots`: immutable section snapshots with stable keys.
- `review_rounds`: immutable revision, round number, snapshotted deadline, and offering-derived participant roster relation. Unique `(run_id, stage, number)` and unique `revision_id`.
- `review_round_participants`: immutable reviewer and source teaching-assignment IDs; unique `(round_id, reviewer_user_id)`.
- `review_decisions`: immutable, unique `(round_id, reviewer_user_id)`, with revision ID matching the round.
- `generation_change_requests`: immutable typed target, field, kind, comment, actor, and timestamp. The target must exist in the named frozen revision, except the whole-outline target.
- `review_round_closures`: immutable administrator action, unique `round_id`, with frozen collated request IDs and close timestamp.
- `generation_jobs`: add outline/content rewrite kinds. A rewrite payload contains only `close_record_id`; unique one job per close record and one model invocation per job.
- Existing `QuestionVersion` and `QuizVersion` rows referenced by a content revision are treated as immutable drafts. Publish materializes only the administrator-selected revision. No review table is joined by student routes.

The leaf revision is the revision without a successor, so no shared mutable “current revision” pointer is required. Concurrent worker/admin successor creation races against the unique parent constraint; the close record and row lock choose the legal writer. Review reads merge immutable per-teacher decisions at the boundary.

## Module map

```text
backend/src/education_platform/
├── core/llm.py                         # existing OpenRouter transport; shared unchanged
├── modules/assistant/
│   ├── strategy.py                     # context union, strategy protocol and registry
│   ├── policy_strategy.py              # current policy graph + handbook retrieval
│   ├── generation_strategy.py          # frozen revision/intake graph and draft-request tool
│   ├── service.py                      # conversation/turn service dispatches strategy
│   └── router.py                       # existing /admin/policy/chats unchanged
└── modules/generation/
    ├── types.py                        # revision, review, command and result domain types
    ├── models.py                       # immutable revision/review persistence rows
    ├── schemas.py                      # HTTP DTO parsing/serialization only
    ├── revisions.py                    # snapshot validation, stable-key diff, materialization
    ├── review.py                       # deep review read/submit/close interface
    ├── rewrite.py                      # one-call outline/content rewrite strategy
    ├── service.py                      # upload/run/retry lifecycle outside review
    ├── router.py                       # thin teaching/admin adapters
    └── worker.py                       # create draft revisions; never accept/publish

frontend/src/
├── api/generation.ts                   # four review/assistant calls
├── api/types.ts                        # discriminated transport types
└── components/
    ├── GenerationReview.tsx            # stage shell and history
    ├── RevisionDiff.tsx                # snapshot-to-snapshot presentation
    ├── ChangeRequestComposer.tsx       # local draft, immutable submit
    └── GenerationAssistant.tsx         # explain/draft only
```

`review.py` is intentionally deep: callers do not coordinate roster checks, decision collection, collation, rewrite limits, revision writes, acceptance, or publication. `revisions.py` is not a public pass-through repository; it owns immutable snapshot validation, stable identity, diffing, and conversion of an accepted snapshot into existing curriculum/material/assessment rows.

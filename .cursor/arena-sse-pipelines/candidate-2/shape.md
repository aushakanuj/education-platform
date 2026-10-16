# Shape — progress subject + wake

Derived from [usage.md](./usage.md). If these disagree, change this file.

## Data structures

Progress is still a **Postgres snapshot**. The new types name *what to watch*, *when to stop*, and *what one connection has already seen*. They are not a log both processes write.

```python
# modules/progress/types.py
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, TypeAlias
from uuid import UUID

from education_platform.modules.generation.schemas import GenerationRunOut
from education_platform.modules.generation.types import RunPhase
from education_platform.modules.rag.schemas import (
    KnowledgeVersionStatusOut,
    MaterialVersionStatusOut,
)


class SubjectKind(StrEnum):
    RUN = "run"
    VERSION = "version"


@dataclass(frozen=True, slots=True)
class RunSubject:
    kind: Literal[SubjectKind.RUN]
    id: UUID

    def key(self) -> str:
        return f"run:{self.id}"


@dataclass(frozen=True, slots=True)
class VersionSubject:
    """Hides curriculum vs knowledge vs topic-intake tables. Resolution is a read."""

    kind: Literal[SubjectKind.VERSION]
    id: UUID

    def key(self) -> str:
        return f"version:{self.id}"


ProgressSubject: TypeAlias = RunSubject | VersionSubject


def run_subject(run_id: UUID) -> RunSubject:
    return RunSubject(kind=SubjectKind.RUN, id=run_id)


def version_subject(version_id: UUID) -> VersionSubject:
    return VersionSubject(kind=SubjectKind.VERSION, id=version_id)


def parse_subject_key(raw: str) -> ProgressSubject:
    """NOTIFY payload → subject. Invalid keys are dropped, not raised into the worker."""
    raise NotImplementedError


class ClosePolicy(StrEnum):
    """Default is implied by subject kind. Callers may override; the upload UI should not."""

    RUN_TERMINAL = "run_terminal"
    RUN_PARKED = "run_parked"
    VERSION_TERMINAL = "version_terminal"


def default_close_policy(subject: ProgressSubject) -> ClosePolicy:
    match subject:
        case RunSubject():
            return ClosePolicy.RUN_TERMINAL
        case VersionSubject():
            return ClosePolicy.VERSION_TERMINAL


_RUN_TRUE_TERMINAL = frozenset({RunPhase.PUBLISHED, RunPhase.FAILED, RunPhase.DISCARDED})
_RUN_HITL = frozenset({RunPhase.OUTLINE_REVIEW, RunPhase.QA_REVIEW})
_VERSION_TERMINAL = frozenset({"ready", "failed", "published", "superseded", "archived"})

ProgressSnapshot: TypeAlias = (
    GenerationRunOut | MaterialVersionStatusOut | KnowledgeVersionStatusOut
)


@dataclass(frozen=True, slots=True)
class EventId:
    """Opaque SSE id. Construct only via event_id_for(snapshot). Not a table row."""

    value: str


def event_id_for(subject: ProgressSubject, snapshot: ProgressSnapshot) -> EventId:
    """Stable hash of the GET JSON that would be sent. Same snapshot → same id."""
    raise NotImplementedError


def event_id_from_header(raw: str | None) -> EventId | None:
    if raw is None or raw.strip() == "":
        return None
    return EventId(raw.strip())


@dataclass(frozen=True, slots=True)
class SnapshotFrame:
    event_id: EventId
    snapshot: ProgressSnapshot
    close_after: bool


@dataclass(frozen=True, slots=True)
class HeartbeatFrame:
    pass


ProgressFrame: TypeAlias = SnapshotFrame | HeartbeatFrame
```

### Close policy (pure)

```python
# modules/progress/close.py

def jobs_in_flight(snapshot: GenerationRunOut) -> bool:
    return any(job.status in ("queued", "running") for job in snapshot.jobs)


def should_close(snapshot: ProgressSnapshot, policy: ClosePolicy) -> bool:
    match policy:
        case ClosePolicy.RUN_TERMINAL:
            if not isinstance(snapshot, GenerationRunOut):
                raise TypeError("RUN_TERMINAL requires a run snapshot")
            return snapshot.phase in _RUN_TRUE_TERMINAL
        case ClosePolicy.RUN_PARKED:
            if not isinstance(snapshot, GenerationRunOut):
                raise TypeError("RUN_PARKED requires a run snapshot")
            if snapshot.phase in _RUN_TRUE_TERMINAL:
                return True
            # generating is worker-busy even when jobs[] is briefly empty
            return snapshot.phase in _RUN_HITL and not jobs_in_flight(snapshot)
        case ClosePolicy.VERSION_TERMINAL:
            if isinstance(snapshot, GenerationRunOut):
                raise TypeError("VERSION_TERMINAL requires a version snapshot")
            return snapshot.lifecycle_status in _VERSION_TERMINAL
```

Invariants encoded here, not in frontend folklore:

- True terminal for a run is `published | failed | discarded` only.
- `generating` never closes a run stream.
- Rewrite under `outline_review` / `qa_review` keeps `RUN_PARKED` open while `jobs[]` is queued/running; `RUN_TERMINAL` (default) never cared.
- Version close uses ingest lifecycle, not `IngestJob.status`.

## Dominant access patterns

### 1. Subscribe (API process, per HTTP connection)

```
authorize subject
→ audit once
→ read snapshot (heal generating jobs on this first read only)
→ emit unless Last-Event-ID matches
→ if should_close: emit with close_after and return
→ loop:
     wait wake(subject) OR heartbeat timeout
     read snapshot (pure)
     if event id changed: emit
     if should_close: close_after and return
     else if wait timed out: HeartbeatFrame
```

Per-connection state is: `subject`, `policy`, `last_emitted: EventId | None`. There is no process-wide event log.

### 2. Wake (worker or API writer, same transaction as the snapshot write)

```
mutate ContentGenerationRun / GenerationJob / SourceMaterialVersion / KnowledgeDocumentVersion
→ publish_wake(session, subject, …)
→ session.commit()   # pg_notify fires after commit
```

One ingest success commit can wake `version:{id}` and `run:{id}` (intake indexing). Claim RUNNING is a snapshot change (`jobs[]`) and must wake the run.

### 3. Reconnect

Client sends `Last-Event-ID`. Server reads current snapshot. Equal id → wait. Different → emit. Missed NOTIFY between reads is recovered by the heartbeat re-read (wake is not a durable queue).

### 4. Rejected pattern: fourth table

Do not add `progress_events`, `sse_cursors`, or a phase-shadow column. Event ids are hashes of the snapshot the GET already returns. If that JSON did not change, nothing is emitted.

## Public signatures

```python
# modules/progress/__init__.py — the module surface
from education_platform.modules.progress.close import should_close
from education_platform.modules.progress.subscribe import subscribe
from education_platform.modules.progress.types import (
    ClosePolicy,
    ProgressFrame,
    ProgressSubject,
    run_subject,
    version_subject,
)
from education_platform.modules.progress.wake import publish_wake

__all__ = [
    "ClosePolicy",
    "ProgressFrame",
    "ProgressSubject",
    "publish_wake",
    "run_subject",
    "should_close",
    "subscribe",
    "version_subject",
]
```

No `asyncpg`, `psycopg`, `NOTIFY`, `StreamingResponse`, or SSE byte strings on this list.

### `subscribe`

```python
# modules/progress/subscribe.py
from collections.abc import AsyncIterator
from typing import Protocol

from education_platform.modules.authorization.scope import Scope
from education_platform.modules.authorization.principal import Principal
from education_platform.modules.progress.types import (
    ClosePolicy,
    EventId,
    HeartbeatFrame,
    ProgressFrame,
    ProgressSnapshot,
    ProgressSubject,
    SnapshotFrame,
)
from education_platform.modules.progress.wake import WakeWaiter


class SnapshotReader(Protocol):
    async def authorize_and_read(
        self,
        principal: Principal,
        scope: Scope,
        subject: ProgressSubject,
        *,
        heal: bool,
    ) -> ProgressSnapshot:
        """Scope + existence. Topic-intake versions 404. heal=True only on first tick."""
        ...


HEARTBEAT_SECONDS = 15.0


async def subscribe(
    principal: Principal,
    scope: Scope,
    subject: ProgressSubject,
    *,
    last_event_id: EventId | None = None,
    close: ClosePolicy | None = None,
    reader: SnapshotReader | None = None,
    wakes: WakeWaiter | None = None,
) -> AsyncIterator[ProgressFrame]:
    """Yield snapshot/heartbeat frames until close policy fires or the iterator is closed.

    Defaults: Postgres LISTEN waiter, Postgres snapshot reader, default_close_policy(subject).
    Tests pass fakes. Does not take a request-scoped AsyncSession.
    """
    policy = close or default_close_policy(subject)
    reader = reader or PostgresSnapshotReader()
    wakes = wakes or PostgresWakeWaiter()
    last = last_event_id
    heal = True
    try:
        while True:
            snapshot = await reader.authorize_and_read(
                principal, scope, subject, heal=heal
            )
            heal = False
            eid = event_id_for(subject, snapshot)
            closing = should_close(snapshot, policy)
            if last is None or eid != last:
                last = eid
                yield SnapshotFrame(event_id=eid, snapshot=snapshot, close_after=closing)
            if closing:
                return
            wait = await wakes.wait(subject, timeout=HEARTBEAT_SECONDS)
            if wait is WakeResult.TIMED_OUT:
                yield HeartbeatFrame()
            # NOTIFIED / TIMED_OUT both fall through to the next read
    finally:
        await wakes.aclose()
```

`# TODO` listen-then-read: `PostgresWakeWaiter.wait` must LISTEN (or already be listening) **before** the next `authorize_and_read` in the loop so a commit that lands during `wait` is not lost. First iteration reads before wait; after the first emit, the waiter stays LISTENing across timeouts.

`# TODO` do not run `_ensure_generating_jobs` on heartbeat ticks. `heal=True` is subscribe-start only. Leftover slice-1 `generating` + empty jobs is a first-read side effect of the existing GET, not a stream protocol.

### `publish_wake`

```python
# modules/progress/wake.py
from enum import StrEnum
from typing import Protocol

PROGRESS_CHANNEL = "education_progress"  # private. not part of subscribe()


class WakeResult(StrEnum):
    NOTIFIED = "notified"
    TIMED_OUT = "timed_out"


class WakeWaiter(Protocol):
    async def wait(self, subject: ProgressSubject, timeout: float) -> WakeResult: ...
    async def aclose(self) -> None: ...


def publish_wake(session: Session | AsyncSession, *subjects: ProgressSubject) -> None:
    """SELECT pg_notify(:channel, :key) on the current transaction. Caller commits.

    Sync Session (worker) and AsyncSession (API) both work; async callers await the
    async variant below. Duplicate keys in one call collapse.
    """
    raise NotImplementedError


async def publish_wake_async(session: AsyncSession, *subjects: ProgressSubject) -> None:
    raise NotImplementedError


class PostgresWakeWaiter:
    """One dedicated LISTEN connection for this SSE client. Not borrowed from the ORM pool.

    Filters NOTIFY payloads with parse_subject_key; other subjects are ignored.
    Timeout → WakeResult.TIMED_OUT (caller emits heartbeat and re-reads anyway).
    """

    async def wait(self, subject: ProgressSubject, timeout: float) -> WakeResult:
        raise NotImplementedError

    async def aclose(self) -> None:
        raise NotImplementedError
```

Do **not** introduce a process-global hub that buffers events. Fan-out is Postgres: every listener on `education_progress` gets every payload and ignores other subjects. Two uvicorn workers each LISTEN; that is correct. Shared state with the worker is the snapshot tables only.

### Snapshot reader (hides tables)

```python
# modules/progress/snapshots.py

class PostgresSnapshotReader:
    async def authorize_and_read(
        self,
        principal: Principal,
        scope: Scope,
        subject: ProgressSubject,
        *,
        heal: bool,
    ) -> ProgressSnapshot:
        match subject:
            case RunSubject(id=run_id):
                return await self._read_run(principal, scope, run_id, heal=heal)
            case VersionSubject(id=version_id):
                return await self._read_version(principal, version_id)

    async def _read_run(self, principal, scope, run_id, *, heal: bool) -> GenerationRunOut:
        # Short-lived session per tick (session factory, not the request session).
        # TODO: generation.service.get_run(..., heal=heal) — heal maps to today's
        # _ensure_generating_jobs. Subsequent ticks call get_run with heal=False
        # plus in_flight_jobs + qa_items_for_run, same assembly as router._run_out.
        raise NotImplementedError

    async def _read_version(self, principal, version_id) -> (
        MaterialVersionStatusOut | KnowledgeVersionStatusOut
    ):
        # Admin only (router already required it; still check institution).
        # 1. SourceMaterialVersion joined to SourceMaterial
        #    - missing → try knowledge
        #    - subtopic_id is None → 404 (topic-intake; use run subject)
        #    - else rag.service.get_material_version_status (404 if not in institution)
        # 2. KnowledgeDocumentVersion → rag.service.get_knowledge_version_status
        # 3. else 404
        raise NotImplementedError
```

`generation.service` and `rag.service` keep owning rows. Progress only chooses which getter and whether to heal. Do not add `GET /ingest-jobs/{id}`.

Small generation change when filling this in: `get_run(..., heal: bool = True)` so GET HTTP stays identical (`heal=True`) and stream ticks can opt out. That is a parameter on an existing function, not a new lifecycle store.

## HTTP adapter (thin)

```python
# modules/progress/router.py + sse.py

async def iter_sse(frames: AsyncIterator[ProgressFrame]) -> AsyncIterator[bytes]:
    """Private. Maps SnapshotFrame → id/event/data; HeartbeatFrame → b': heartbeat\\n\\n'."""
    raise NotImplementedError
```

`StreamingResponse` lives here only. Mount next to existing routers in `main.py` (`/api/v1`). Generation and rag routers do not grow stream endpoints — that would be candidate-1 (one stream per GET).

Version admin audit: one `record_event` at subscribe start for `progress.version.get` (or reuse the existing version GET resource name). Generation uses `scoped("teaching.generation.get")` once, as in usage.

## Frontend

```ts
// frontend/src/api/progress.ts
export type ProgressSubject =
  | { kind: "run"; id: string }
  | { kind: "version"; id: string };

export function runSubject(id: string): ProgressSubject {
  return { kind: "run", id };
}
export function versionSubject(id: string): ProgressSubject {
  return { kind: "version", id };
}

export type Snapshot = GenerationRun | MaterialVersionStatus | KnowledgeDocumentVersionStatus;

export async function subscribeProgress(
  subject: ProgressSubject,
  options: {
    signal?: AbortSignal;
    lastEventId?: string;
    onSnapshot: (snapshot: Snapshot) => void;
  },
): Promise<void> {
  // fetch GET /progress/runs/:id or /progress/versions/:id
  // Authorization Bearer via getAccessToken(); AbortSignal; parse SSE
  // on snapshot: onSnapshot(); remember lastEventId
  // on drop before terminal: reconnect with Last-Event-ID unless aborted
  // native EventSource is forbidden (no Bearer)
  throw new Error("not implemented");
}

export async function watchProgress(
  subject: ProgressSubject,
  options: { signal?: AbortSignal; onSnapshot?: (snapshot: Snapshot) => void } = {},
): Promise<Snapshot> {
  let last: Snapshot | undefined;
  await subscribeProgress(subject, {
    signal: options.signal,
    onSnapshot: (snapshot) => {
      last = snapshot;
      options.onSnapshot?.(snapshot);
    },
  });
  if (last === undefined) throw new Error("progress stream closed without a snapshot");
  return last;
}
```

```ts
// frontend/src/api/client.ts — additive
export async function apiStream(
  path: string,
  options: { signal?: AbortSignal; lastEventId?: string },
): Promise<Response> {
  // same base URL + Bearer + 401 refresh as apiRequest; do not parse the body as JSON
  throw new Error("not implemented");
}
```

`pollGenerationRun` / `pollWhileGenerating` / `pollMaterialVersionStatus` / `pollKnowledgeDocumentVersionStatus` become wrappers around `watchProgress` only if a test still names them; the upload UI calls `subscribeProgress` directly. Do not keep `intervalMs` as a required part of the new path.

Discriminate version JSON with existing fields (`source_material_id` vs `document_id`), not a new envelope.

## Module map

```
modules/progress/
  __init__.py      # public names
  types.py         # subjects, EventId, frames
  close.py         # should_close (pure)
  snapshots.py     # PostgresSnapshotReader
  wake.py          # publish_wake, PostgresWakeWaiter
  subscribe.py     # the loop
  sse.py           # bytes; imported by router only
  router.py        # two GETs

generation/service.py   # get_run(..., heal: bool = True) when implemented
generation/worker.py    # publish_wake next to existing commits
workers/ingest.py       # publish_wake on success/fail commits
review.py / service.py  # publish_wake on accept/discard/retry/reject/publish/rewrite enqueue

frontend/src/api/progress.ts
frontend/src/api/client.ts   # apiStream
```

Call chain for a tick: `router.py` → `subscribe.py` → (`snapshots.py` | `wake.py`). Three files. `sse.py` is the HTTP encoder, not a fourth domain layer.

## Tests without a live worker

- `should_close` table: every `RunPhase` × empty/non-empty jobs; version statuses.
- `subscribe` with `FakeWakeWaiter` (an `asyncio.Event` the test sets) and a reader that returns canned `GenerationRunOut` values. Assert emit / skip-same-id / heartbeat / close-after-published.
- Router test: 401 without Bearer, 403 teacher on version subject, 404 topic-intake version, 200 `text/event-stream` first snapshot equals GET JSON.
- `publish_wake` unit: SQL contains `pg_notify` and the subject key; no JSON body.

## Deliberately not done

- Redis, Kafka, MinIO, worker HTTP, FastAPI-lifespan worker, `EventSource` cookies.
- Percent, parse/chunk/embed events, `IngestJob` as client protocol.
- LLM token streams (assistant/policy/review chats stay POST).
- Student-facing progress routes.
- `sse_starlette` types on `subscribe`.
- A global in-API event buffer both the worker and the API write.

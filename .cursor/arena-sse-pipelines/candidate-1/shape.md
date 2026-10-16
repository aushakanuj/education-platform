# Shape — snapshot stream (candidate 1)

Derived from [usage.md](usage.md). If they diverge, change this file.

## Module map

```
education_platform/core/sse.py
  encode_frames, replay_until_close, StreamClock
  owns: tick sleep, skip-unchanged, heartbeat comments, SSE bytes, disconnect
  does not own: GenerationRun, version status, close tables, auth

education_platform/modules/generation/progress.py
  snapshot_run, generation_disposition, watch_run
  owns: GET-equivalent snapshot + generation close table
  calls: service.get_run, in_flight_jobs, qa_items_for_run

education_platform/modules/rag/progress.py
  watch_material_version, watch_knowledge_version, ingest_disposition
  owns: ingest close table; loaders are today's get_*_version_status

generation/router.py   GET .../generation-runs/{id}/events
materials/router.py    GET .../material-versions/{id}/events
rag/router.py          GET .../knowledge-document-versions/{id}/events
  thin: role deps, scoped audit once, anext prime for JSON 404, StreamingResponse

frontend/src/api/client.ts        watchSnapshotStream (fetch + Bearer + reconnect)
frontend/src/api/generation.ts    watchGenerationRun
frontend/src/api/adminIngest.ts   watchMaterialVersionStatus, watchKnowledgeDocumentVersionStatus
```

Call chain for one subscribe (three new files, then today's snapshot owner):

1. `generation/router.py` `stream_show`
2. `generation/progress.py` `watch_run` (disposition + `snapshot_run`)
3. `core/sse.py` `replay_until_close` → `encode_frames`

`service.get_run` is the existing GET fourth hop, not a new layer.

Worker, `IngestJob`, and FastAPI lifespan are out of the map.

## Data structures first

### Close is a type, not a frontend `switch`

```python
from enum import StrEnum
from typing import Literal

class GenerationDisposition(StrEnum):
    """Every GenerationRunOut maps to exactly one of these."""

    WORKER_MOVING = "worker_moving"
    """phase in {indexing, outlining, generating} — jobs[] may be empty (indexing is IngestJob)."""

    REWRITE_RUNNING = "rewrite_running"
    """phase in {outline_review, qa_review} and jobs[] non-empty. Rewrite does not change phase."""

    HITL_PARK = "hitl_park"
    """phase in {outline_review, qa_review} and jobs[] empty. Human work, not worker work."""

    TERMINAL = "terminal"
    """phase in {published, failed, discarded}."""


class GenerationCloseReason(StrEnum):
    HITL_PARK = "hitl_park"
    TERMINAL = "terminal"


def generation_disposition(snapshot: GenerationRunOut) -> GenerationDisposition:
    """Invariant: generating is never HITL_PARK or TERMINAL.

    indexing has jobs [] on purpose (intake is IngestJob). That is WORKER_MOVING,
    not a park. Do not close because jobs is empty.
    """
    raise NotImplementedError


def generation_close_reason(disposition: GenerationDisposition) -> GenerationCloseReason | None:
    """None → keep streaming. HITL_PARK and TERMINAL close. WORKER_MOVING and REWRITE_RUNNING do not."""
    raise NotImplementedError
```

```python
class IngestDisposition(StrEnum):
    PROCESSING = "processing"  # lifecycle_status is processing (or draft, if it ever appears)
    TERMINAL = "terminal"      # ready | failed | published | superseded | archived


def ingest_disposition(lifecycle_status: str) -> IngestDisposition:
    raise NotImplementedError
```

These functions are the single source of truth. Frontend `isTerminalGenerationPhase` (which today returns true for `generating`) is **not** consulted by the watcher. Stepper code may still switch on `phase` for chrome; it must not decide reconnect.

### Frames the helper understands (not FastAPI types)

```python
from dataclasses import dataclass
from typing import Generic, TypeVar

TSnapshot = TypeVar("TSnapshot")  # GenerationRunOut | MaterialVersionStatusOut | KnowledgeVersionStatusOut


@dataclass(frozen=True, slots=True)
class SnapshotFrame(Generic[TSnapshot]):
    kind: Literal["snapshot"]
    body: TSnapshot
    fingerprint: str


@dataclass(frozen=True, slots=True)
class HeartbeatFrame:
    kind: Literal["heartbeat"]


@dataclass(frozen=True, slots=True)
class CloseFrame:
    kind: Literal["close"]
    reason: Literal["hitl_park", "terminal"]


@dataclass(frozen=True, slots=True)
class ErrorFrame:
    kind: Literal["error"]
    status: int
    detail: str


ProgressFrame = SnapshotFrame[TSnapshot] | HeartbeatFrame | CloseFrame | ErrorFrame
```

`StreamingResponse`, `Request`, and raw `bytes` do not appear on `watch_run`. `encode_frames` is the only function that speaks SSE. Pydantic `GenerationRunOut` on `SnapshotFrame.body` is the existing GET document, not a second wire schema.

### Snapshot source (bound inside watch_*, not passed by routers)

```python
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class SnapshotSource(Generic[TSnapshot]):
    """Policy object. Routers never construct this; watch_run / watch_*_version do."""

    load: Callable[[AsyncSession], Awaitable[TSnapshot]]
    fingerprint: Callable[[TSnapshot], str]
    close_reason: Callable[[TSnapshot], Literal["hitl_park", "terminal"] | None]
```

`fingerprint` for generation is canonical `GenerationRunOut.model_dump_json()` (phase, `jobs[]`, outline, qa, markdown all participate so the stepper cannot stall on a silent jobs change). For versions: canonical status JSON (`lifecycle_status`, `chunk_count`, `failure_reason`).

### Clock (tests inject; HTTP does not)

```python
from datetime import timedelta


@dataclass(frozen=True, slots=True)
class StreamClock:
    tick: timedelta = timedelta(milliseconds=500)
    heartbeat: timedelta = timedelta(seconds=15)
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep  # TODO: default asyncio.sleep
```

500ms is ~3× today's poll without `NOTIFY`. Heartbeats fire only when no snapshot has been emitted for `heartbeat` (HITL parks close, so idle hours are not a case). No query param.

## Dominant access patterns

### 1. Subscribe until park (generation)

```
anext(watch_run)
  peek_session: snapshot_run = get_run + in_flight_jobs + qa_items_for_run
  _ensure_generating_jobs runs here (same as GET)
  emit SnapshotFrame
  if close_reason: emit CloseFrame; stop
loop (new session each tick):
  sleep(tick)
  snapshot_run again
  if fingerprint unchanged: maybe HeartbeatFrame; continue
  emit SnapshotFrame
  if close_reason: emit CloseFrame; stop
  if DomainError: emit ErrorFrame; stop
```

`get_run` every tick, not a second read-only API. `_ensure_generating_jobs` is idempotent; leftover `generating` + `jobs: []` recovers on the first tick and stays recovered. Cost: two extra job SELECTs per tick. Accepted vs inventing `read_run`.

### 2. Reconnect after refresh

`listTopicGenerationRuns` then `watchGenerationRun(id)`. No event log. Ignore `Last-Event-ID` if a proxy adds it. First frame is current snapshot; if already parked, immediate close.

### 3. Rewrite under the same HITL phase

Close-round queues `rewrite_outline` / `rewrite_content`. Phase stays `outline_review` / `qa_review`. Previous stream already sent `close: hitl_park`. UI subscribes again. Disposition is `REWRITE_RUNNING` until `jobs[]` empty, then `HITL_PARK` close.

### 4. Curriculum / knowledge ingest

Same loop, `load = get_material_version_status` / `get_knowledge_version_status`. Topic-intake versions still 404 (`subtopic_id is None`) — do not special-case them onto this stream. Indexing progress for generation lives on the run.

### 5. Shared memory

There is none. Worker commits Postgres. API re-queries. Two API workers streaming the same run each loop independently. Do not add a process-local dict of subscribers.

## Signatures

### `core/sse.py`

```python
async def replay_until_close(
    source: SnapshotSource[TSnapshot],
    *,
    sessions: async_sessionmaker[AsyncSession],
    clock: StreamClock,
    peek_session: AsyncSession | None = None,
) -> AsyncIterator[ProgressFrame[TSnapshot]]:
    """Open peek_session (or a factory session) for the first load; then factory per tick.

    Invariant: never yield a second SnapshotFrame with the same fingerprint.
    Always yield the first snapshot even when close_reason is already set, then CloseFrame.
    HeartbeatFrame is comments only, produced here, not by SnapshotSource.
    Cancel / GeneratorExit ends the iterator; do not write a close reason for disconnect.
    """
    raise NotImplementedError
    # TODO: commit after each load so get_run's ensure-jobs flush is visible to the worker.
    # TODO: on DomainError after the stream has started, yield ErrorFrame and return
    #       (do not raise into StreamingResponse after headers).


async def encode_frames(
    first: ProgressFrame[TSnapshot],
    rest: AsyncIterator[ProgressFrame[TSnapshot]],
) -> AsyncIterator[bytes]:
    """SSE: event/data for snapshot+close+error; ': keepalive\\n\\n' for heartbeat.

    snapshot data = first.body.model_dump_json() for Pydantic snapshots.
    close data = {"reason": "hitl_park"|"terminal"}.
    error data = {"detail": str, "status": int}.
    """
    raise NotImplementedError
```

### `generation/progress.py`

```python
async def snapshot_run(
    session: AsyncSession, scope: Scope, run_id: UUID
) -> GenerationRunOut:
    """Lift of router._run_out. GET show and the stream both call this."""
    raise NotImplementedError


async def watch_run(
    scope: Scope,
    run_id: UUID,
    *,
    peek_session: AsyncSession,
    sessions: async_sessionmaker[AsyncSession] | None = None,
    clock: StreamClock | None = None,
) -> AsyncIterator[ProgressFrame[GenerationRunOut]]:
    """Bind SnapshotSource with generation_disposition and snapshot_run; replay_until_close.

    peek_session is required so the router can 404 before StreamingResponse.
    Default sessions = get_session_factory(); default clock = StreamClock().
    """
    raise NotImplementedError
```

`watch_run` is not a pass-through: it is where `generating` is forbidden as a close, rewrite-vs-park is decided, and GET assembly is bound. Routers do not receive `SnapshotSource`.

### `rag/progress.py`

```python
async def watch_material_version(
    principal: Principal,
    version_id: UUID,
    *,
    peek_session: AsyncSession,
    sessions: async_sessionmaker[AsyncSession] | None = None,
    clock: StreamClock | None = None,
) -> AsyncIterator[ProgressFrame[MaterialVersionStatusOut]]:
    raise NotImplementedError


async def watch_knowledge_version(
    principal: Principal,
    version_id: UUID,
    *,
    peek_session: AsyncSession,
    sessions: async_sessionmaker[AsyncSession] | None = None,
    clock: StreamClock | None = None,
) -> AsyncIterator[ProgressFrame[KnowledgeVersionStatusOut]]:
    raise NotImplementedError
```

Loads call existing `rag.service.get_material_version_status` / `get_knowledge_version_status` (404 for foreign institution and for intake SMVs). Close via `ingest_disposition`.

### HTTP

Keep JSON GET. Add:

- `GET /api/v1/teaching/generation-runs/{run_id}/events` — teacher+admin, `scoped("teaching.generation.stream")`
- `GET /api/v1/admin/material-versions/{version_id}/events` — administrator
- `GET /api/v1/admin/knowledge-document-versions/{version_id}/events` — administrator

Audit once after successful `anext`. Do not call `scoped()` per tick. Student routes unchanged.

### Frontend

```ts
export type StreamCloseReason = "hitl_park" | "terminal";

export async function watchSnapshotStream<T>(
  path: string,
  options: {
    signal?: AbortSignal;
    onSnapshot?: (snapshot: T) => void;
  },
): Promise<{ snapshot: T; reason: StreamCloseReason }> {
  // fetch(`${base}/api/v1${path}`, { headers: { Authorization, Accept: text/event-stream }, signal })
  // 401 → same refresh-once behavior as apiRequest, then retry the stream
  // parse event: / data:  (ignore comment lines)
  // snapshot → onSnapshot, remember last
  // close → return { snapshot: last, reason }
  // drop without close → backoff reconnect (new fetch; first snapshot is current)
  // abort → AbortError, no reconnect
  throw new Error("not implemented");
}
```

`watchGenerationRun` / `watchMaterialVersionStatus` / `watchKnowledgeDocumentVersionStatus` only supply the path and return `snapshot`. They do not take `intervalMs`. Delete `pollGenerationRun`, `pollWhileGenerating`, `pollMaterialVersionStatus`, `pollKnowledgeDocumentVersionStatus`.

## Invariants

- Payload of `event: snapshot` is today's GET model. No percent field. No `ingest_job` object.
- API process streams; worker process writes rows. No shared queue.
- `generation_disposition("generating")` is `WORKER_MOVING` even when `jobs == []`.
- `outline_review`/`qa_review` with jobs is not a close.
- Heartbeats are not snapshots; clients must not call `onUpdate` for comments.
- Disconnect ≠ `close`. Only `event: close` stops client reconnect.
- Validation at the subscribe boundary (auth, 404). Inside the loop, trust `snapshot_run` / version-status.

## Deliberately not in this sketch

- `LISTEN/NOTIFY` or a unified `subscribe(run:id|version:id)` (candidate 2).
- `sse_starlette` (not in the repo).
- GET on `ingest_jobs`.
- Worker changes, percent, parse/chunk/embed event types.
- Holding the request `AsyncSession` across `sleep`.
- Per-tick `SCOPED_READ`.
- A fourth lifecycle table beside `phase` / `lifecycle_status`.

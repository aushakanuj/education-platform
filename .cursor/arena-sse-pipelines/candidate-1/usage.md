# Snapshot streams for pipeline progress

Replace 1.5s JSON GET polling with Server-Sent Events on the **API process**. Each stream is a live `GET` of today's snapshot: generation `GenerationRunOut`, curriculum `MaterialVersionStatusOut`, knowledge `KnowledgeVersionStatusOut`. The worker still only commits Postgres rows. There is no Redis, `NOTIFY`, in-memory bus, or worker HTTP.

Callers import domain watchers (`generation.progress.watch_run`, `rag.progress.watch_material_version`, `rag.progress.watch_knowledge_version`) plus one shared SSE encoder. They never import `IngestJob`, tick intervals, heartbeat comments, or `StreamingResponse` from a service module.

Existing JSON GETs stay. Streams sit **next to** them (`.../events`). Auth is the same role+scope as the GET they sit next to. Students never see these routes.

## Quickstart

```python
# API process only. Worker does not call this.
from education_platform.modules.generation.progress import watch_run
from education_platform.core.sse import encode_frames

# Router has already authenticated (teacher|admin + teaching scope)
# and opened one SCOPED_READ. Prime the iterator so 404 is JSON, not a hung stream.
stream = watch_run(scope, run_id, peek_session=request.session)
first = await anext(stream)          # SnapshotFrame; raises GenerationError on miss
await request.record_rows(1, detail=f"stream={run_id}")
return StreamingResponse(
    encode_frames(first, stream),
    media_type="text/event-stream",
    headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
)
```

The frontend does **not** use `EventSource` (no `Authorization` header). One shared `fetch` reader:

```ts
const settled = await watchGenerationRun(runId, { signal, onUpdate: trackRun });
// settled.phase is a HITL park (outline_review | qa_review) or true terminal
// (published | failed | discarded). It is never "generating".
```

Wire events the reader already understands:

```
event: snapshot
data: { ...GenerationRunOut... }

: keepalive

event: close
data: {"reason":"hitl_park"}
```

`data` on `snapshot` is **byte-identical** to today's GET JSON (same Pydantic model). `close` is stream control, not a new progress protocol. Heartbeats are SSE comments; the client ignores them.

## Close policy the caller relies on

The server decides when to stop. The UI does not chain two pollers and does not treat `generating` as terminal.

| Snapshot | `jobs[]` | Stream |
| --- | --- | --- |
| `indexing` / `outlining` / `generating` | anything | **keep open** (`worker_moving`) |
| `outline_review` / `qa_review` | non-empty (rewrite) | **keep open** (`rewrite_running`) |
| `outline_review` / `qa_review` | empty | **close** `hitl_park` |
| `published` / `failed` / `discarded` | ignored | **close** `terminal` |

Subscribe while already parked: one `snapshot` then `close`. Subscribe during rewrite under the same HITL phase: stay open until `jobs[]` empties (or the run fails). After `accept-outline`, the UI opens a **new** subscribe; that one stays open through `generating` until `qa_review` or a true terminal.

Curriculum / knowledge streams close only on ingest terminals already used by pollers: `ready | failed | published | superseded | archived`. They stay open on `processing`. Topic-intake indexing is **not** a material-version stream; it is `run.phase === "indexing"` on the generation stream.

## What the caller does not do

- Does not start the worker in FastAPI lifespan, and does not `GET /ingest-jobs/{id}`.
- Does not send `Last-Event-ID` as a log offset. Reconnect is a new subscribe; the first event is the current GET snapshot.
- Does not pass tick/heartbeat intervals on the query string. Those are inside the encoder loop.
- Does not invent `percent`, parse/chunk/embed stages, or `queued` vs `running` ingest events (the worker does not commit them onto version rows).
- Does not audit every tick. One `SCOPED_READ` per subscribe.
- Does not use cookie `EventSource` as a substitute for Bearer.

---

## Call site 1 — generation router next to `show`

Today `GET /teaching/generation-runs/{id}` builds `GenerationRunOut` via `_run_out` (`get_run` + `in_flight_jobs` + `qa_items_for_run`). The stream route reuses that assembler and the same role deps.

```python
# backend/src/education_platform/modules/generation/router.py

@router.get(
    "/teaching/generation-runs/{run_id}/events",
    dependencies=[Depends(require_role("teacher", "administrator"))],
)
async def stream_show(
    run_id: UUID,
    request: ScopedRequest = Depends(scoped("teaching.generation.stream")),
) -> StreamingResponse:
    stream = watch_run(request.scope, run_id, peek_session=request.session)
    first = await anext(stream)
    await request.record_rows(1, detail=f"stream={run_id}")
    return StreamingResponse(encode_frames(first, stream), media_type="text/event-stream", headers=SSE_HEADERS)
```

`GET /admin/material-versions/{id}/events` and `GET /admin/knowledge-document-versions/{id}/events` look the same: administrator-only, prime `anext` so "Version not found" stays a JSON 404 (including topic-intake SMVs that already 404 on the JSON GET), one audit row, then bytes. Materials/knowledge routers stay thin; `rag.progress` owns version snapshots and ingest close policy.

The request `AsyncSession` is **only** for the primed snapshot + audit commit. After `StreamingResponse` starts, each later tick opens a short session from `get_session_factory()` and commits (so leftover `generating` recovery in `get_run` still persists). The request session is not held across sleeps.

---

## Call site 2 — worker commit (unchanged)

```python
# backend/src/education_platform/modules/generation/worker.py  — no SSE imports

def _complete_job(session: Session, job: GenerationJob, run: ContentGenerationRun) -> None:
    job.status = GenerationJobStatus.SUCCEEDED
    # phase may move outlining → outline_review, generating → qa_review, etc.
    session.commit()
    # Deliberately nothing else: no NOTIFY, no HTTP POST, no in-memory queue.
    # The API stream notices on its next re-query of snapshot_run.
```

Ingest success still commits version `ready` + `chunk_count` together and, for topic intake, `on_intake_indexed` moves the run to `outlining`. The generation stream sees `indexing` then `outlining` as two snapshots. Curriculum/knowledge streams see `processing` then `ready`. Per-node LLM `flush()` stays invisible, same as today's GET.

Tests drive a stream without a live worker: insert a run, `anext` until the first snapshot, mutate `phase` / `jobs` in another session, advance a fake clock, assert the next `snapshot` / `close`.

---

## Call site 3 — `TopicGenerationUpload` replaces the dual poller

Today the stepper parks `pollGenerationRun` at `isTerminalGenerationPhase`, which **includes `generating`**, then chains `pollWhileGenerating`. That folklore moves into the server close table above. One watcher, used at real parks:

```ts
// frontend/src/api/generation.ts
import { watchSnapshotStream } from "./client";
import type { GenerationRun } from "./types";

export async function watchGenerationRun(
  runId: string,
  options: { signal?: AbortSignal; onUpdate?: (run: GenerationRun) => void } = {},
): Promise<GenerationRun> {
  const { snapshot } = await watchSnapshotStream<GenerationRun>(
    `/teaching/generation-runs/${encodeURIComponent(runId)}/events`,
    { signal: options.signal, onSnapshot: options.onUpdate },
  );
  return snapshot;
}
```

```ts
// frontend/src/components/TopicGenerationUpload.tsx  (replace pollUntilSettled / pollGeneratingToQa)

async function watchUntilPark(runId: string, abort: AbortController) {
  const settled = await watchGenerationRun(runId, { signal: abort.signal, onUpdate: trackRun });
  if (abort.signal.aborted) return;
  trackRun(settled);
  if (settled.phase === "outline_review" || settled.phase === "qa_review") {
    const review = await getGenerationReview(settled.id);
    if (!abort.signal.aborted) setWorkspace(review);
  }
}

// after submit, or when listed run is indexing/outlining:
await watchUntilPark(runId, abort);

// after accept-outline (phase is generating — stream #1 already closed at outline_review):
if (!abort.signal.aborted) setBusy(false);
await watchUntilPark(runId, abort); // stays open through generating → qa_review

// after close-round rewrite (phase still outline_review|qa_review, jobs non-empty):
await watchUntilPark(runId, abort); // stays open until rewrite jobs vanish
```

`onUpdate` still drives the stepper from `phase` + `jobs[]`. Un-busy during `generating` is a UI reaction to a snapshot, not a stream-close rule. `pollGenerationRun` / `pollWhileGenerating` / `intervalMs` go away. `getGenerationRun` remains for one-shot reads.

Knowledge-doc and curriculum pollers switch the same way:

```ts
await watchKnowledgeDocumentVersionStatus(accepted.version_id, { signal });
await watchMaterialVersionStatus(accepted.version_id, { signal });
```

Both call `watchSnapshotStream` with their `/events` path. Unexpected disconnect (no `close` event) reconnects behind `watchSnapshotStream`; a `close` event stops. Heartbeat comments are not snapshots.

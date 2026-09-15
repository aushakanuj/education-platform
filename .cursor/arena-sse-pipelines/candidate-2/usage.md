# Progress subjects — caller usage

The UI stops polling. It subscribes to a **subject** (`run:{id}` or `version:{id}`). The API keeps one long-lived `text/event-stream` open, waits for a Postgres wake, re-reads today's GET snapshot, and writes an SSE `snapshot` event when that JSON changed. The worker still only commits rows. It never builds wire JSON.

Existing one-shot GETs stay. This replaces the 1.5s pollers only.

## What you import

Backend (the public surface):

```python
from education_platform.modules.progress import (
    ClosePolicy,
    publish_wake,
    run_subject,
    subscribe,
    version_subject,
)
```

Frontend:

```ts
import {
  subscribeProgress,
  watchProgress,
  runSubject,
  versionSubject,
} from "../api/progress";
```

`subscribe` / `subscribeProgress` hide generation vs ingest tables, close policy, heartbeats, and `Last-Event-ID`. Callers do not pass tick intervals, do not chain a second waiter for `generating`, and do not mention `LISTEN`/`NOTIFY`.

## Subjects

| Subject | Who may subscribe | Snapshot JSON (unchanged GET body) | Stream closes when |
| --- | --- | --- | --- |
| `run:{uuid}` | teacher or admin, same topic scope as `GET /teaching/generation-runs/{id}` | `GenerationRunOut` | phase is `published` \| `failed` \| `discarded` (default `ClosePolicy.RUN_TERMINAL`) |
| `version:{uuid}` | administrator | `MaterialVersionStatusOut` **or** `KnowledgeVersionStatusOut` | `lifecycle_status` is `ready` \| `failed` \| `published` \| `superseded` \| `archived` |

`version:{id}` is one subject. The reader decides which version table to load. Topic-intake versions (`source_material.subtopic_id is None`) 404 here — indexing progress lives on `run:{id}`, never on a material-version GET.

Default close for runs stays open through `outline_review`, rewrite jobs that do not change phase, `generating`, and `qa_review`. HITL is a snapshot the UI already handles; it is not a reason to tear down the stream. Heartbeat comments keep the connection alive while a human is deciding.

`ClosePolicy.RUN_PARKED` exists for tests or a caller that truly wants “return when the worker is idle for a human.” The generation upload UI should not use it. `generating` is never parked: empty `jobs[]` during `generating` is healed once at subscribe start, then the stream waits for `qa_review` / failure.

## HTTP

```
GET /api/v1/progress/runs/{run_id}
GET /api/v1/progress/versions/{version_id}

Authorization: Bearer <access>
Accept: text/event-stream
Last-Event-ID: <optional, from a previous snapshot>
```

Native `EventSource` cannot set Bearer. The client uses `fetch` + `ReadableStream` (same auth path as `apiRequest`, plus `AbortSignal`).

On subscribe the server emits the current snapshot unless `Last-Event-ID` already matches it, then waits. Heartbeats are SSE comments (`: heartbeat`). A terminal snapshot is the last event; the response then ends. Clients reconnect on drop **only** when the last event was not terminal.

`SCOPED_READ` / admin auth is recorded **once per subscribe**, not per tick.

## Wire (private to the HTTP adapter)

```
id: run:3f2a…:a1b2c3d4
event: snapshot
data: {"id":"…","phase":"outlining","jobs":[{"kind":"outline","status":"running"}],…}

: heartbeat
```

`data` is exactly today's GET JSON. No percent. No ingest-job row. No parse/chunk/embed stages.

---

## Call site 1 — thin FastAPI route

`modules/progress/router.py`. Auth + path → subject. Domain loop yields frames. This file only maps frames to bytes.

```python
@router.get("/progress/runs/{run_id}")
async def run_events(
    run_id: UUID,
    request: Request,
    principal: Principal = Depends(require_role("teacher", "administrator")),
) -> StreamingResponse:
    # One-shot session: scope + SCOPED_READ, then close. Do not hold get_session for the stream.
    scope = await authorize_run_subscribe(principal, run_id)
    frames = subscribe(
        principal,
        scope,
        run_subject(run_id),
        last_event_id=event_id_from_header(request.headers.get("last-event-id")),
    )
    return StreamingResponse(
        iter_sse(frames),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/progress/versions/{version_id}")
async def version_events(
    version_id: UUID,
    request: Request,
    principal: Principal = Depends(require_administrator),
) -> StreamingResponse:
    # Short session for scope + one SCOPED_READ, closed before the stream starts.
    subject = version_subject(version_id)
    frames = subscribe(
        principal,
        await scope_for_principal(principal),
        subject,
        last_event_id=event_id_from_header(request.headers.get("last-event-id")),
    )
    return StreamingResponse(iter_sse(frames), media_type="text/event-stream", ...)
```

Do not `Depends(get_session)` for the life of the stream. `subscribe` opens a short session per snapshot read. The request session is only for the one-shot auth/audit.

`GET /teaching/generation-runs/{id}` and the two admin version GETs remain for one-shot reads and list/reconnect bootstrap.

---

## Call site 2 — worker (and API) after-commit wake

The worker still commits the same rows. In the **same transaction**, it publishes a subject key. Payload is the subject string, not an event body.

```python
# workers/ingest.py — success commit (already calls on_intake_indexed)
version.lifecycle_status = SourceMaterialVersionStatus.READY
on_intake_indexed(session, version.id)  # may flip a run to outlining + outline job
job.status = IngestJobStatus.SUCCEEDED
publish_wake(session, version_subject(version.id))
if (run_id := indexing_run_id(session, version.id)) is not None:
    publish_wake(session, run_subject(run_id))
session.commit()  # NOTIFY delivered after this commit
```

```python
# generation/worker.py — existing _complete_job / _fail_job_and_run / claim RUNNING
def _complete_job(session: Session, job_id: UUID, *, ok_phases: frozenset[RunPhase]) -> None:
    ...
    publish_wake(session, run_subject(job.run_id))
    session.commit()
```

API mutations that change a snapshot a live stream cares about (accept, discard, retry, reject-items, publish, enqueue rewrite) call the same `publish_wake` before the request-scoped `session.commit()`. A teacher who accepted in this tab, or another tab, wakes every subscriber. If NOTIFY is missed, the next heartbeat re-read still converges.

`publish_wake` is sync-or-async session `execute(pg_notify)`. It is not a second microservice and not an HTTP call into the worker.

---

## Call site 3 — `TopicGenerationUpload` (replaces dual pollers)

Today: `pollGenerationRun` until a folklore “terminal” that includes `generating`, then `pollWhileGenerating`. After refresh, the same chain.

Replacement: one subscription for the in-flight run. HITL buttons are driven by `onUpdate` (`phase === "outline_review"` etc.). Accept/publish stay POST. The stream stays open and the next wake is `generating` / `qa_review` / `published`.

```ts
// frontend/src/components/TopicGenerationUpload.tsx
pollAbortRef.current?.abort();
const abort = new AbortController();
pollAbortRef.current = abort;

const listed = await listTopicGenerationRuns(topicId);
const current = inFlightRun(listed);
if (!current) return;
setRun(current);

await subscribeProgress(runSubject(current.id), {
  signal: abort.signal,
  onSnapshot: (run) => {
    trackRun(run);
    if (run.phase === "outline_review" || run.phase === "qa_review") {
      void getGenerationReview(run.id).then(setWorkspace);
    }
  },
});
```

Submit / accept / retry keep their POSTs, then the already-open subscription (or a new one after 202) receives the next snapshots. No `intervalMs`. No second waiter.

Knowledge-doc and curriculum pollers use the same helper, different subject:

```ts
const settled = await watchProgress(versionSubject(accepted.version_id), { signal });
// settled is MaterialVersionStatus | KnowledgeDocumentVersionStatus
// stream already closed on ready | failed | …
```

`watchProgress` is `subscribeProgress` that resolves with the last snapshot when the server closes. Ingest UIs can keep an `await`. The generation stepper should use `onSnapshot` so HITL is not blocked on stream end.

Reconnect after refresh: `listTopicGenerationRuns` (existing GET) → `subscribeProgress(runSubject(id))`. Pass `lastEventId` only when this browser already saw a snapshot this session; a full refresh starts from the current GET-equivalent snapshot.

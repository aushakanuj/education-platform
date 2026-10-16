# Progress subjects — synthesized usage

The UI stops polling. It subscribes to a **subject** (`run:{id}` or `version:{id}`). The API keeps one `text/event-stream` open, waits for a Postgres wake, re-reads today's GET snapshot, and writes an SSE `snapshot` when that JSON changed. The worker still only commits rows. It never builds wire JSON.

Existing one-shot GETs stay. This replaces the 1.5s pollers.

## What you import

```python
from education_platform.modules.progress import (
    publish_wake,
    run_subject,
    subscribe,
    version_subject,
)
```

```ts
import { subscribeProgress, watchProgress, runSubject, versionSubject } from "../api/progress";
```

Callers do not pass tick intervals, do not chain a second waiter for `generating`, and do not mention `LISTEN`/`NOTIFY`.

## Subjects

| Subject | Who may subscribe | Snapshot JSON | Stream closes when |
| --- | --- | --- | --- |
| `run:{uuid}` | teacher or admin, same scope as `GET /teaching/generation-runs/{id}` | `GenerationRunOut` | phase is `published` \| `failed` \| `discarded` |
| `version:{uuid}` | administrator | `MaterialVersionStatusOut` **or** `KnowledgeVersionStatusOut` | `lifecycle_status` is `ready` \| `failed` \| `published` \| `superseded` \| `archived` |

`version:{id}` 404s topic-intake versions (`subtopic_id is None`). Indexing progress lives on `run:{id}`.

Run streams stay open through `outline_review`, rewrite jobs, `generating`, and `qa_review`. HITL is a snapshot. `generating` never closes the stream.

## HTTP

```
GET /api/v1/progress/runs/{run_id}
GET /api/v1/progress/versions/{version_id}

Authorization: Bearer <access>
Accept: text/event-stream
```

Native `EventSource` cannot set Bearer. Use `fetch` + `ReadableStream`.

Prime the first snapshot **before** `StreamingResponse` so missing subjects are JSON 404. One `SCOPED_READ` / admin audit per subscribe, not per tick.

## Wire

```
id: run:<uuid>:<fingerprint>
event: snapshot
data: { ...today's GET JSON... }

: heartbeat

event: close
data: {"reason":"terminal"}
```

No percent. No ingest-job row. Heartbeats are comments. Stop reconnect only on `event: close`.

---

## Call site 1 — thin FastAPI route

Auth + path → subject. First `anext` for JSON 404. Then bytes.

```python
@router.get("/progress/runs/{run_id}")
async def run_events(
    run_id: UUID,
    principal: Principal = Depends(require_role("teacher", "administrator")),
) -> StreamingResponse:
    ...
```

Do not hold the request `AsyncSession` for the life of the stream.

## Call site 2 — worker after-commit wake

```python
publish_wake(session, run_subject(job.run_id))
session.commit()
```

Ingest success also wakes `version:{id}` and, when a run is indexing that version, `run:{id}`. Payload is the subject key, not an event body. API mutations (accept, discard, retry, reject-items, publish, rewrite) call `publish_wake_async` on the request session.

## Call site 3 — `TopicGenerationUpload`

One `subscribeProgress(runSubject(id), { onSnapshot })` for the in-flight run. HITL buttons are driven by snapshots. Accept/publish stay POST; the open stream receives `generating` / `qa_review` / `published`. Ingest UIs `await watchProgress(versionSubject(id))`.

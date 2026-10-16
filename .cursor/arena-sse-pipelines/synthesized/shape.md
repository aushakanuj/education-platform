# Shape — progress subject + Postgres wake (synthesized)

Derived from [usage.md](usage.md). Base: candidate-2. Grafts from candidate-1: wire `event: close`, internal `GenerationDisposition` (no exported `ClosePolicy`), prime `anext` before `StreamingResponse`, heal once.

## Module map

```
education_platform/modules/progress/
  types.py       RunSubject / VersionSubject, frames, event_id_for
  close.py       GenerationDisposition, should_close (HITL does not close)
  wake.py        publish_wake / publish_wake_async, PostgresWakeWaiter
  snapshots.py   PostgresSnapshotReader (GET assembly; topic-intake versions 404)
  subscribe.py   LISTEN-first, heal-once, skip-unchanged, heartbeat, CloseFrame
  sse.py         iter_sse + SSE_HEADERS
  router.py      GET /progress/runs/{id}  GET /progress/versions/{id}

frontend/src/api/client.ts      apiStream (Bearer + text/event-stream)
frontend/src/api/progress.ts    subscribeProgress / watchProgress / runSubject / versionSubject
frontend/src/api/generation.ts  subscribeGenerationRun
frontend/src/api/adminIngest.ts watchMaterialVersionStatus / watchKnowledgeDocumentVersionStatus
```

Call chain: thin router → `subscribe` → (`PostgresSnapshotReader` | `PostgresWakeWaiter`) → `iter_sse`.

Worker stays commit-only except `publish_wake` in the same transaction as the snapshot. No Redis/Kafka/MinIO. FastAPI lifespan does not start the worker.

## Close is internal

```python
class GenerationDisposition(StrEnum):
    WORKER_MOVING = "worker_moving"      # indexing | outlining | generating
    REWRITE_RUNNING = "rewrite_running"  # HITL phase + in-flight jobs
    HITL_PARK = "hitl_park"              # outline_review | qa_review, jobs empty
    TERMINAL = "terminal"                # published | failed | discarded


def should_close(snapshot) -> bool:
    """Run streams close only on TERMINAL. generating never closes. HITL never closes."""
```

Do **not** export `ClosePolicy`. Callers do not choose park vs terminal.

Version streams close when `lifecycle_status` is `ready | failed | published | superseded | archived`.

## HTTP

```
GET /api/v1/progress/runs/{run_id}         teacher | administrator
GET /api/v1/progress/versions/{version_id} administrator
```

Prime `anext` before `StreamingResponse` so missing subjects are JSON 404. One `SCOPED_READ` per subscribe. Do not hold the request `AsyncSession` for the stream lifetime: peek session for the first read, factory sessions after.

`version:{id}` 404s topic-intake source-material versions (`subtopic_id is None`). Indexing lives on `run:{id}`.

## Wire

```
id: run:<uuid>:<fingerprint>
event: snapshot
data: <today's GET JSON>

: heartbeat

event: close
data: {"reason":"terminal"}
```

Fingerprint is a hash of the GET JSON. Same snapshot → no emit. Heartbeat 15s also recovers a missed `NOTIFY`. Stop reconnect only on `event: close`. Disconnect ≠ settled.

## Wake

Channel `education_progress`. Payload is the subject key (`run:{uuid}` / `version:{uuid}`), not wire JSON.

```
mutate row
→ publish_wake(session, run_subject(...), ...)
→ session.commit()   # pg_notify fires after commit
```

LISTEN is a dedicated asyncpg connection per SSE client, not an in-memory hub. `get_run(..., heal=True)` only on the first peek.

## Tests without a live worker

- `should_close` / `generation_disposition` for generating, HITL, rewrite, true terminal, version ready
- `subscribe` with `FakeWakeWaiter` + canned snapshots (heal-once, skip-unchanged, heartbeat, close)
- `publish_wake` records unique `pg_notify` keys
- Router: 401, student 403 on versions, JSON 404, failed-run stream snapshot+close

## Deliberately not done

- Redis, Kafka, MinIO, worker HTTP, FastAPI-lifespan worker, native `EventSource`
- Percent, parse/chunk/embed events, `GET /ingest-jobs/{id}`
- LLM token streams
- Student-facing progress routes
- `sse_starlette`, `progress_events` table, exported `ClosePolicy`

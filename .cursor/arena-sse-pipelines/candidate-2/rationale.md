## Problem

Generation runs and RAG ingest versions today move only when a worker commits a Postgres snapshot; the UI discovers that by GET-polling every 1.5s. API and worker are separate processes (asyncpg vs psycopg), FastAPI does not run the worker, and there is no bus both can see. The non-obvious part is not “add SSE”: it is doing so without a second store, without teaching callers which table just changed (`GenerationJob` vs `IngestJob` vs version rows), without turning `generating` + dual pollers into a second protocol, and without the worker emitting wire JSON it does not own. Constraints: existing `GenerationRunOut` / version-status JSON, teacher+admin scope on runs, admin-only versions, 404 topic-intake on material-version GET, Bearer (not cookie `EventSource`), student APIs untouched.

## Usage (caller's view)

Callers subscribe to `run:{id}` or `version:{id}` and receive today's GET JSON until a typed close policy fires. Workers (and API writers) only `publish_wake(session, subject)` in the same transaction as the snapshot they already commit. The generation stepper uses one `subscribeProgress` with `onSnapshot` instead of `pollGenerationRun` then `pollWhileGenerating`. Ingest UIs `await watchProgress(versionSubject(id))`. Full README and three call sites: [usage.md](./usage.md). Types in [shape.md](./shape.md) are derived from that.

## Shape

A `progress` module owned by neither generation nor rag. The load-bearing structure is `ProgressSubject` + `ClosePolicy` + `EventId` (hash of the GET JSON) + per-connection `{subject, last_emitted}`. Worker writes rows and `pg_notify('education_progress', subject_key)`. API `subscribe()` LISTENs on a dedicated connection, re-reads via existing getters, and yields `SnapshotFrame | HeartbeatFrame`. The router is the only place `StreamingResponse` / SSE bytes appear.

Validation at the subscribe boundary: role+scope, topic-intake 404, institution check. Inside the loop, trust `should_close` and event-id equality (`boundary-discipline`, `encode-lessons-in-structure`). `_ensure_generating_jobs` runs once (`heal=True`); later ticks are pure reads so SSE is not an enqueue pump. Audit once per subscribe. Heartbeat (~15s) is both proxy keepalive and missed-NOTIFY recovery — wake is not a durable queue (`separate-before-serializing-shared-state`: the only shared writer is Postgres; the API does not append a log the worker also writes).

Interface depth: two HTTP paths and two frontend functions hide table choice, close/HITL/rewrite policy, LISTEN, heal-once, heartbeat, and reconnect. Callers still see subject kind (they know whether they uploaded a run or a version) and the existing snapshot JSON. That is as small as the product allows: merging run and version payloads would invent an envelope. Compared with one stream glued to each GET plus an API sleep loop, this surface is smaller and the callee does more.

Deliberately not done: percent, ingest-job polling, parse/chunk/embed stages, a `progress_events` table that must stay in sync with `phase`, worker HTTP, Redis.

## Synthesis decision

Filled by arena after pick.

## Tradeoffs accepted

- We accept one extra Postgres connection per SSE client (dedicated LISTEN) in exchange for no in-process event hub that looks like shared mutable state with the worker.
- We accept HITL streams that stay open with heartbeats in exchange for deleting the dual `generating` waiter from the caller protocol.
- We accept lossy NOTIFY (wake-only) plus a 15s re-read in exchange for not storing a replay log beside `phase`.
- We accept a first-tick `get_run` side effect (`heal`) in exchange for not inventing a second “repair leftover jobs” path; we refuse to run it every tick.
- We accept one `SCOPED_READ` per subscribe, not per event, in exchange for not flooding audit on heartbeats.
- We accept `publish_wake` call sites next to existing commits (worker and accept/publish/rewrite) in exchange for not wrapping SQLAlchemy in a generic outbox.

## Alternatives considered

- **One stream per existing GET + API busy-loop (candidate-1).** Generation router streams `get_run` every 1.5s; rag router streams each version GET. Worker unchanged. Callers still know two URLs, still chain waiters or inherit `isTerminalGenerationPhase` folklore, and the API burns queries while HITL is idle. The public surface is larger and hides less (tick interval, table choice, close policy stay with callers). Rejected on interface depth; process-safety is fine but the design is a shallow pass-through around today's pollers.
- **Worker emits SSE JSON / writes an events table.** Would make the unauthenticated worker an event author and require a fourth lifecycle store in sync with `phase`. Rejected: snapshot remains canonical; wake payload is a subject key only.

## Open questions and risks

- Is 15s the heartbeat we want in front of school proxies, or should it be configurable without becoming a caller-facing poll interval?
- If SSE concurrency grows past a handful of teachers, should LISTEN move to one process-wide waiter, and does that reintroduce the in-memory fan-out we refused?
- Should `get_run(heal=False)` be a documented service flag for all readers, or a progress-only wrapper so HTTP GET cannot accidentally skip heal?
- Do accept/publish in a second browser tab need to be called out in the upload UI, or is “the open stream wakes” enough?
- Are rewrite jobs under HITL something the stepper must render from `jobs[]`, now that the stream no longer parks and misses them?

## Next implementation step

Add `modules/progress` types + pure `should_close` tests, then `publish_wake` on one ingest success commit and a `subscribe` loop driven by `FakeWakeWaiter` that emits existing `GenerationRunOut` JSON.

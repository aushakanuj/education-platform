# Rationale

## Problem

Generation and RAG progress are Postgres snapshots that the UI learns about by polling `GET` every 1.5s. The worker that writes those rows is a separate process with a different DB driver and no HTTP server, so a live stream cannot be a queue both sides share. The non-obvious part is close policy: today's frontend treats `generating` as terminal (`isTerminalGenerationPhase`) and then starts a second poller, while rewrite jobs leave `outline_review`/`qa_review` unchanged so a parked poller never sees them. The stream has to encode HITL park vs true terminal vs rewrite-still-running in types, reuse existing GET JSON, keep generation and rag as snapshot owners, and still hide tick/heartbeat/reconnect behind a small surface — without `NOTIFY`, Redis, or attaching HTTP to the worker.

## Usage (caller's view)

Routers add `GET .../events` next to the existing JSON GETs, prime `anext(watch_run(...))` so 404 stays JSON, record one `SCOPED_READ`, and return `StreamingResponse(encode_frames(...))`. The worker's `_complete_job` / ingest success commit is unchanged. `TopicGenerationUpload` calls `watchGenerationRun` at real parks (after submit, after accept-outline, after rewrite) instead of `pollGenerationRun` + `pollWhileGenerating`. Knowledge-doc and curriculum pollers call the same `watchSnapshotStream` helper with their `/events` paths. Full README and the three call sites: [usage.md](usage.md).

## Shape

Postgres remains canonical. Each API tick re-queries the same assembler as GET (`snapshot_run` = `get_run` + in-flight jobs + QA items; rag version-status functions unchanged). `GenerationDisposition` / `IngestDisposition` are the load-bearing types: `generating` is always `WORKER_MOVING`; HITL phases with `jobs[]` are `REWRITE_RUNNING`; empty HITL jobs are `HITL_PARK`; `published|failed|discarded` (and ingest `ready|failed|...`) are `TERMINAL`. Only the last two produce `CloseFrame`.

The public surface is three `watch_*` functions plus `encode_frames` / `watchSnapshotStream`. That surface hides session-per-tick, fingerprint skip, heartbeat comments, dual-poller folklore, and reconnect-on-drop. It exposes snapshot JSON the UI already renders and a close reason so disconnect ≠ park. Tick/heartbeat live on `StreamClock`, injected in tests, never on the query string. Transport types (`StreamingResponse`, SSE bytes) stay in the router + `core/sse`; progress modules yield `ProgressFrame`. Auth is the existing role+scope on the sibling GET. Audit is once per subscribe. `Last-Event-ID` is ignored because there is no event log.

Interface depth: routers do not orchestrate intervals or generating waiters; they authenticate and map 404. `watch_run` is where close policy is bound, not a pass-through of `get_run` in a loop. `core/sse.replay_until_close` is shared so generation and rag do not copy the sleep/heartbeat loop, but they still own fingerprints and close tables (per boundary-discipline, per encode-lessons-in-structure). Shared state is "nothing" — each stream is a private cursor over rows the worker already wrote (per separate-before-serializing-shared-state). Call chain is three files.

## Synthesis decision

Filled by arena after pick.

## Tradeoffs accepted

- We accept API-side re-query (~500ms, skip-unchanged) in exchange for a worker that stays unaware of subscribers and for tests that mutate rows without a live worker or `NOTIFY`.
- We accept extra job SELECTs every tick via `get_run` (including `_ensure_generating_jobs`) in exchange for one snapshot assembler shared with JSON GET, not a second read path.
- We accept closing at HITL parks (UI re-subscribes after accept/rewrite) in exchange for not holding hour-long streams with heartbeats while a human reviews.
- We accept sending full `GenerationRunOut` (outline, qa_items, lesson markdown) on each *changed* snapshot in exchange for not inventing a progress DTO that can drift from GET.
- We accept ignoring `Last-Event-ID` in exchange for not pretending a snapshot database is an event log.
- We accept one `SCOPED_READ` per subscribe, not per tick, in exchange for not flooding audit on a 10-minute generating run.

## Alternatives considered

- **Unified subscribe-by-subject + worker `NOTIFY` (candidate 2).** One `subscribe(run:{id}|version:{id})` hides which table the worker wrote and wakes the API without a busy loop. It exposes a new subject vocabulary to every caller, requires worker (or after-commit) coupling, and still must assemble GET snapshots at the read boundary. Interface looks smaller until close policy, 404 rules (intake SMVs), and authz per resource leak back out of the generic subject. Rejected for this candidate: generation and rag already own snapshots; a shared encoder is enough depth without a shared subscribe noun.
- **Keep the dual poller, only swap transport.** Stream closes at `isTerminalGenerationPhase` including `generating`, then the UI opens a second stream. Callers still orchestrate two waiters; rewrite-under-HITL stays folklore. Shallow — the SSE layer hides nothing the pollers already got wrong.
- **Stay open through HITL with heartbeats until `published`.** One subscribe from upload to publish. Exposes the client to hours of idle TCP and forces the server to distinguish "human is thinking" from "socket died" without a close type. Parks are the real product seams (review workspace loads there); closing at parks is the smaller public story.

## Open questions and risks

- How many concurrent teacher streams are we willing to run at 500ms ticks against `get_run` (QA item assembly included) before we should slow the clock, skip QA on non-`qa_review` ticks, or revisit `NOTIFY` as wake-up only?
- Should `watchSnapshotStream` refresh the access token mid-stream if a generating run outlives JWT TTL, or is reconnect-after-401 enough?
- Do we cap a `WORKER_MOVING` stream (stuck worker / never-committed ingest) so a forgotten tab cannot sit on a session forever?
- Is `X-Accel-Buffering: no` plus comment heartbeats enough for the proxies this deployment actually uses, or is there another buffer we have not seen?

## Next implementation step

Write `generation_disposition` / `generation_close_reason` unit tests, then `replay_until_close` with a fake `StreamClock` and a stub `SnapshotSource`, before any FastAPI route.

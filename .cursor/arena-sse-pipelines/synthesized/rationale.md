# Rationale

## Problem

Generation and RAG progress are Postgres snapshots the UI used to learn about by polling GET every 1.5s. The worker that writes those rows is a separate process with a different DB driver and no HTTP server, so a live stream cannot be a queue both sides share. The non-obvious part is close policy: today's frontend treated `generating` as terminal and then started a second poller, while rewrite jobs leave `outline_review`/`qa_review` unchanged so a parked poller never sees them. The stream has to encode HITL park vs true terminal vs rewrite-still-running in types, reuse existing GET JSON, and still hide LISTEN/heartbeat/reconnect — without Redis, Kafka, or attaching HTTP to the worker.

## Usage (caller's view)

One progress module. Callers subscribe to a subject (`run:{id}` or `version:{id}`) and receive today's GET JSON as `event: snapshot` until `event: close`. The worker still only commits rows, plus `publish_wake` in that same transaction. `TopicGenerationUpload` keeps one `subscribeGenerationRun` open through HITL, rewrite, and `generating`. Knowledge-doc and curriculum ingest `await watchProgress(versionSubject(id))`. Full README: [usage.md](usage.md).

## Shape

Postgres remains canonical. Each tick re-queries the GET assembler after a `NOTIFY` or heartbeat. `GenerationDisposition` is internal: `generating` is always `WORKER_MOVING`; HITL with `jobs[]` is `REWRITE_RUNNING`; empty HITL jobs are `HITL_PARK`; only `published|failed|discarded` (and ingest terminals) close the stream. `ClosePolicy` is not exported.

The public surface is `subscribe` / `publish_wake` / `run_subject` / `version_subject`. Transport bytes stay in `sse.py` + the thin router. First peek heals leftover generating jobs (same as GET); later ticks are `heal=False`. Audit once per subscribe. `Last-Event-ID` is a snapshot fingerprint, not an event-log offset.

## Synthesis decision

**Base: candidate-2 (progress subject + Postgres wake).** Cross-judge scored interface depth 5 vs 3: one `subscribe(run:|version:)` covers knowledge-doc ingest and generation rewrite without a park-re-subscribe protocol or a second `generating` waiter. Both candidates scored 5 on process safety (`NOTIFY` is same-transaction Postgres, not a broker). FRAME asked for the shape a maintainer extends without teaching a second protocol — that is candidate-2.

**Grafted from candidate-1:**

1. Wire `event: close` with `{"reason":"terminal"}`. Disconnect ≠ settled; reconnect only when the stream drops without close.
2. Internal `GenerationDisposition`. Do not export `ClosePolicy`. Run streams stay open through HITL/rewrite/`generating`.
3. Prime `anext` before `StreamingResponse` so 404 stays JSON. Share GET assembly. `heal=True` only on the first peek.

**Rejected from candidate-1:** one `/events` path per existing GET, API busy-loop as the wake, closing at HITL parks as the caller protocol.

## Tradeoffs accepted

- We accept `publish_wake` at every snapshot commit in exchange for one subscribe surface that survives HITL and rewrite.
- We accept a dedicated LISTEN connection per SSE client in exchange for not introducing Redis or an in-memory hub the worker cannot see.
- We accept holding the run stream through human review in exchange for not teaching a park-re-subscribe dance.
- We accept sending full GET JSON on each changed snapshot in exchange for not inventing a progress DTO that can drift from GET.
- We accept one `SCOPED_READ` per subscribe, not per tick.
- We accept heartbeat re-read (15s) as the recovery path for a missed `NOTIFY`.

## Alternatives considered

- **Per-GET `/events` busy-loop (candidate 1).** Worker stays unaware of subscribers. Callers still pick among three routes and re-subscribe after every HITL park. Rejected: that is the protocol you would re-teach for every new pipeline.
- **Keep the dual poller, only swap transport.** Stream closes at `isTerminalGenerationPhase` including `generating`. Callers still orchestrate two waiters. Shallow.
- **Close at HITL parks.** Product seams exist there, but rewrite jobs do not change phase, so a closed stream misses them unless every button re-subscribes.

## Open questions and risks

- Forgotten `publish_wake` stalls the UI until the next heartbeat — tests should pin commit-site wakes.
- Should `apiStream` refresh JWT mid-stream, or is reconnect-after-401 enough?
- Do we cap a `WORKER_MOVING` stream so a forgotten tab cannot sit forever if the worker is stuck?
- Is `X-Accel-Buffering: no` plus comment heartbeats enough for the proxies this deployment uses?

## Next implementation step

Done in this change: `progress` module, worker/API wakes, `apiStream` + `subscribeProgress`, upload/ingest UIs off the 1.5s pollers.

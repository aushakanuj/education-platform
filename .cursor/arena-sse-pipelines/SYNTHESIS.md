# Arena synthesis — SSE pipelines

## Candidates

- [candidate-1](candidate-1/) snapshot stream (worker unchanged, GET-next-to-events)
- [candidate-2](candidate-2/) progress subject + Postgres wake (`NOTIFY`)

## Base

**candidate-2.** Cross-judge ([Cross-judge SSE sketches](c1e79f51-8a6d-4c98-866e-88e3b3070058)) scored interface depth 5 vs 3: one `subscribe(run:|version:)` covers knowledge-doc ingest and generation rewrite without a park-re-subscribe protocol or a second `generating` waiter. Parent had picked candidate-1 for worker isolation; both scored 5 on process safety (`NOTIFY` is same-transaction Postgres, not a broker). The FRAME asked for the shape a maintainer extends without teaching a second protocol — that is candidate-2.

## Grafts (from candidate-1)

1. Wire `event: close` with `{"reason":"terminal"}`. Disconnect ≠ settled; reconnect only when the stream drops without close.
2. Internal `GenerationDisposition` (`WORKER_MOVING` / `REWRITE_RUNNING` / `HITL_PARK` / `TERMINAL`). Do **not** export `ClosePolicy`. Run streams stay open through HITL/rewrite/`generating`; only `published|failed|discarded` close.
3. Prime `anext` before `StreamingResponse` so 404 stays JSON. Share GET assembly (`get_run` + in-flight jobs + qa items). `heal=True` only on the first peek.

## Rejected (from candidate-1)

- One `/events` path per existing GET
- API busy-loop as the wake mechanism
- Closing at HITL parks as the default caller protocol

## Dropouts

None.

## Verification

Synthesized usage/shape/rationale under `synthesized/` match this record. Red flags: do not export `ClosePolicy`; subject keys stay inside `publish_wake` / LISTEN filter; `PostgresSnapshotReader` keeps intake-404 and heal-once rather than remaining a hollow switch.

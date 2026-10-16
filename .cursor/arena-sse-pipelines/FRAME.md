# Arena frame: SSE for generation + RAG pipelines

## Artifact

Each candidate writes three files under its output dir:

- `usage.md` — README-style caller view plus 2–3 realistic call sites (FastAPI route, worker commit, frontend poller replacement). Usage is the spec.
- `shape.md` — types, signatures, module map, `not implemented` bodies / TODO pseudocode. Derived from usage.
- `rationale.md` — shaped per architect `references/rationale-template.md`. Leave **Synthesis decision** as a placeholder.

## Directions (exhaust the design space)

Whole-shape alternatives, not point fixes.

1. **candidate-1 — Snapshot stream.** FastAPI `StreamingResponse` next to existing GETs. Re-query `get_run` / version-status until the stream should close. Worker unchanged. Payload = today's `GenerationRunOut` / version-status JSON. Shared framing helper only; generation and rag keep owning their snapshots.
2. **candidate-2 — Progress subject + wake.** A single subscribe-by-subject API (`run:{id}` / `version:{id}`) that hides which table the worker wrote. Worker (or a thin after-commit hook) publishes a wake (`NOTIFY` or equivalent Postgres-only signal) so the API does not busy-loop. Domain events are still assembled from existing snapshots at the read boundary — do not make the worker emit wire JSON. Contrast: one deep subscribe surface vs one stream per existing GET.

Do **not** converge on a safe middle. Each runner owns its assigned direction and should reject the other shape in Alternatives considered.

## Rubric (picker)

1. **Process safety.** API process streams; worker process writes Postgres. No in-memory queue across processes. No Redis/Kafka/MinIO.
2. **Interface depth.** Callers (frontend pollers, thin routers) should not orchestrate tick intervals, dual generating waiters, or ingest vs generation tables. Prefer a small subscribe surface that hides close/heartbeat/reconnect policy.
3. **Auth and ownership.** Reuse existing role+scope. Do not leak `IngestJob` as the client protocol. Topic-intake indexing stays on the generation run, not material-version GET.
4. **Existing snapshot fidelity.** Events are today's GET JSON (or a documented strict subset). No invented percent. HITL parks, rewrite-under-same-phase, and `generating` vs true terminal are encoded in types/policy, not left as frontend folklore.
5. **Repo fit.** Thin HTTP, logic in services. Frontend `fetch` + Bearer, not `EventSource`. Tests can drive the stream without a live worker.
6. **Red flags.** Reject shallow pass-through routers, wire-type leakage (`sse_starlette` objects on the service API), temporal parse/chunk/embed modules that duplicate ingest, and a fourth lifecycle table that must stay in sync with `phase`.

## Cross-judge

After both candidates land, score each criterion 1–5 and recommend a base. Prefer the shape a maintainer can extend to knowledge-doc ingest and generation rewrite without teaching callers a second protocol.

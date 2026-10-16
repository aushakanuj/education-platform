# Grounding: pipeline + RAG progress, and where SSE attaches

Repo: `/Users/aushakanuz/Documents/studies/education-platform`

Explainer: last assistant message in
`/Users/aushakanuz/.cursor/projects/Users-aushakanuz-Documents-studies-education-platform/agent-transcripts/` (parent chat, how explainer `a341e988-2d99-43ce-af53-ad3b240599e0`).

## Product intent

Replace 1.5s JSON GET polling for **generation runs** and **RAG ingest versions** with Server-Sent Events so the UI updates as soon as the worker commits a new snapshot. Do not add Redis, Kafka, MinIO, LangGraph, or a second microservice. Do not attach HTTP to the worker process.

This is worker-progress SSE, not LLM token streaming of assistant/policy/review chats.

## How progress works today

Progress is a **Postgres snapshot**, not a live stream.

- Worker (`python -m education_platform.workers` → `runner.run_forever`) claims `ingest_jobs` first, else `generation_jobs`, via `FOR UPDATE SKIP LOCKED`. One job at a time. 1.5s idle sleep.
- FastAPI `lifespan` does **not** start the worker. API and worker are separate processes, different engines (asyncpg vs psycopg). No shared memory.
- There is no SSE, WebSocket, `LISTEN/NOTIFY`, or in-memory bus that both processes can see.
- Redis `ingest_jobs.redis_job_id` was dropped (`d4e5f6a7b8c9`).

```text
POST 202 (enqueue) → worker commits status on Postgres → GET poll 1.5s → UI stepper
```

### Generation

- Aggregate: `ContentGenerationRun.phase` (`indexing` → `outlining` → `outline_review` → `generating` → `qa_review` → `published`, plus `failed`/`discarded`).
- Jobs: `outline | items | lesson | regenerate_items | rewrite_outline | rewrite_content` with `queued | running | succeeded | failed`.
- HTTP: `GET /api/v1/teaching/generation-runs/{id}` → `GenerationRunOut` via `router._run_out` / `service.get_run` + `in_flight_jobs`.
- `jobs[]` is **queued/running only**. Succeeded jobs vanish. During `indexing`, `jobs: []` because indexing is an `IngestJob`, not a `GenerationJob`.
- Submit: admin-only `POST /admin/topics/{id}/generation-runs` 202 `{run_id, topic_id, phase}`. Teachers GET, cannot upload (`TEACHER_UPLOAD_GONE`).
- After accept: items **and** lesson both queued. Single worker runs them sequentially. Phase stays `generating` until both drafts exist.
- Rewrite jobs do **not** change phase; existing pollers have already parked at HITL.
- GET is not a pure read: `_ensure_generating_jobs` can enqueue leftover items/lesson jobs.
- Every teaching GET writes `SCOPED_READ` audit.

Worker generation commits only at claim RUNNING, process start RUNNING, `_complete_job`, `_fail_job_and_run`. Per-node `flush()` is invisible to HTTP. No percent field.

### RAG ingest

- `IngestJob` is observability in the DB. Clients **never** poll it. No `GET /ingest-jobs/{id}`. `ingest_job_id` is on 202 then unused.
- Curriculum: `GET /admin/material-versions/{id}` — admin. Topic-intake versions **404** here (`subtopic_id is None`).
- Knowledge: `GET /admin/knowledge-document-versions/{id}` — admin.
- Version lifecycle: already `processing` at enqueue. `queued` vs `running` is invisible. `chunk_count` jumps 0→N at the same commit as `ready`.
- Topic generation indexing waits on `run.phase=indexing` until `on_intake_indexed` (same ingest success commit) sets `outlining` + outline job.

### Frontend

- Pollers in `frontend/src/api/generation.ts` and `adminIngest.ts`, default 1500ms.
- `pollGenerationRun` stops at `isTerminalGenerationPhase` which includes `generating`. UI **must** chain `pollWhileGenerating`.
- `TopicGenerationUpload` stepper uses `phase` + `jobs[]`. Reconnect after refresh: list runs, GET by id.
- Auth: `apiRequest` always `Authorization: Bearer`. Native `EventSource` **cannot** set that header. Use `fetch` + `ReadableStream`.
- `apiRequest` has no `AbortSignal`; poll abort only cancels sleep.
- Chats are blocking POSTs — out of scope.

## Constraints the design must honor

- Student APIs unchanged. No student-facing ingest/generation streams.
- Keep HTTP routes thin. Logic in module services.
- Auth stays existing role+scope: generation GET teacher+admin scoped; version GETs administrator-only; submit admin-only.
- Postgres snapshot remains canonical. Do not invent percent unless the worker starts committing it.
- No Redis/Kafka/MinIO/second microservice (AGENTS.md, Compose Postgres-only, generation HANDOFF).
- Worker stays unauthenticated. Auth on enqueue and on stream subscribe.
- SSE lives on the API process. Worker has no HTTP server.
- Do not 404-poll topic-intake via material-version GET.
- Dual-poller `generating` semantics and rewrite-while-HITL-phase must be designed, not inherited accidentally.
- CORS already allows `:5173` with credentials; that is not a substitute for Bearer.

## Orchestrator product calls (do not reopen)

1. V1 streams **existing snapshot JSON** (generation run and/or version status), not LLM tokens and not inventing a percent protocol.
2. One shared client consumption path: `fetch` + Bearer + `text/event-stream`. Not cookie `EventSource`.
3. Generation is the primary UX (`TopicGenerationUpload`). Standalone RAG version streams ship in the same design so knowledge-doc and curriculum pollers can switch, even if curriculum UI is currently orphaned.
4. Do not start the worker inside FastAPI lifespan.
5. Do not add a GET on `ingest_jobs` as the generation indexing protocol.

## Open questions the sketch must pick (with a reason)

- API-side re-query loop vs worker `NOTIFY` after existing commits vs both (NOTIFY as wake-up only).
- One stream module owned by neither generation nor rag vs SSE helpers inside each module's router/service.
- When a generation stream closes: true terminal (`published|failed|discarded`) vs HITL parks vs `jobs[]` empty. Rewrite under `outline_review`/`qa_review`.
- Whether `get_run` side-effect `_ensure_generating_jobs` runs on every SSE tick.
- Whether SCOPED_READ audit fires per event or once per subscribe.
- Last-Event-ID / reconnect: replay from GET snapshot vs event ids.
- Heartbeat comments to keep proxies from killing idle HITL streams.
- Whether ingest `queued`/`running` or parse/chunk/embed ever become events (requires worker writes that do not exist today).

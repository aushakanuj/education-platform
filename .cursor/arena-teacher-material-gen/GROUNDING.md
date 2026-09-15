# Grounding (how synthesis)

Full explainer: last assistant message in
`/Users/aushakanuz/.cursor/projects/Users-aushakanuz-Documents-studies-education-platform/agent-transcripts/c972ae52-8c0d-4c8b-a376-e6221f6ec8bc/subagents/aed49464-5b7e-4fb7-a7f2-485f0489a9dc.jsonl`

Repo: `/Users/aushakanuz/Documents/studies/education-platform`

## Product intent

Teacher uploads a source PDF. Existing `ingest_jobs` + Docling worker indexes it. Generated lesson (and quiz if in scope) stay invisible to students until a human approves. Reuse the worker. Do not add LangGraph, a second microservice, Redis, or MinIO.

## Constraints the design must honor

- Student visibility is `SourceMaterialVersion.lifecycle_status=published` AND non-empty `content_markdown`.
- Worker today stops at `READY`, no markdown, no quizzes, no publish.
- `SourceMaterial.slug == "lesson"` is shared by seed and PDF ingest. `published_material_version` picks max version_number across all published materials under a subtopic.
- Ingest HTTP and version status GET are `require_administrator`. Teacher JWT cannot upload today.
- Teacher reach is `TeachingAssignment` / `Scope.taught_offering_ids`. Authoring already uses that.
- Authoring `DRAFT → publish_draft` is teacher self-publish of questions. It does not attach `QuizItem`s. Design 02 says teachers do not publish common SourceCurriculum in the POC. User asked for teacher frontend plus an approval process.
- Worker is unauthenticated. Auth belongs on enqueue and on publish.
- Keep HTTP routes thin. Logic in module services.
- Student quiz APIs must not expose answer keys.
- At most one published version per `source_material_id`.
- POC Demo School has no teacher. Live teacher is Al Noor Meera after synthetic CLI.

## Orchestrator product calls (do not reopen these)

1. The teacher who can teach the offering is the approver. Administrators may approve too (unrestricted). No supervisor-batch inbox in v1.
2. Worker stays at `READY` (or a generation-complete non-published status) until explicit publish. Never auto-publish.
3. V1 ships teacher upload + index + lesson markdown generation + teacher preview + approve/discard. Quiz generation in v1 only if it reuses existing quiz tables without Bloom/80-item/LangGraph machinery. Prefer a small released quiz bound on approve over a new assessment stack.
4. Do not supersede the seeded common lesson until the teacher approves. While READY, students keep seeing existing published markdown.
5. Do not introduce Docling-as-a-service, LangGraph, message brokers, or MinIO.

## Open questions the sketch must pick (with a reason)

- Same `"lesson"` slug vs new material identity vs resolver change.
- Where generation runs (same worker after READY, new `IngestTargetKind`, API-side job).
- Teacher routes vs `/admin/...` with teacher JWT.
- Extra version statuses vs READY + markdown as "awaiting approval".
- How quiz attach works if included.
- Frontend: extend `SubjectMaterialsPage` vs new teacher generate page vs copy question bank.

# Arena frame: topic-grain generation sketch

## Artifact

Each candidate: `usage.md` + `shape.md` + `rationale.md` for the FastAPI generation pipeline (topic grain, two HITL, ingest_jobs + Docling, no extra brokers).

## Directions (exhaust the design space)

1. **candidate-1:** `GenerationRun` aggregate. SMV is intake/publish only.
2. **candidate-2:** No run table. Curriculum graph + topic-scoped SMV is the workflow.

## Rubric (picker)

1. **Product grain.** Topic study lesson; subtopics diagnostic; two HITL; admin READY index-only; worker never auto-publishes.
2. **Student isolation.** Student visibility remains published/released; keys off student paths; no second student-visibility table.
3. **Interface depth.** Small public surface (submit / get / outline edit / accept / later QA publish). Callers do not orchestrate stages or know ingest job ids.
4. **Invariants in types/schema.** In-flight per topic, XOR material parent, quotas sum, match-or-create only on accept, idempotent transitions.
5. **Repo fit.** Reuses ingest_jobs + Docling + pgvector + existing Question/QuizScope; no LangGraph/Redis/MinIO/new microservice; `IngestTargetKind` stays table-shaped.
6. **Slice 1 startability.** Outline HITL can ship without 60–80 item gen or teacher UI, without painting the rest into a corner.

## Cross-judge

After both candidates land, score each criterion 1–5 and recommend a base. Prefer the shape a maintainer can extend (items, lesson, QA) without breaking student switches.

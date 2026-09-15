# Rationale

## Problem

Teachers need to turn a topic PDF into one student lesson plus a 60–80 item `topic_mastery` bank, with two human gates, without any of that work becoming student-visible until publish. The system already indexes PDFs (`ingest_jobs` → Docling → READY) and already publishes lessons as `SourceMaterialVersion.published`. Same morning we stretched that version row into a subtopic `LessonProposal` (`id == version.id`, `awaiting_approval`, ~5 questions). Product then moved the grain: **topic**, not teacher-picked `subtopic_id`; outline HITL before expensive gen; one topic lesson; items as diagnostic tags. `SourceMaterialVersion` is the wrong aggregate for that (no outline, no item bank, `READY` already means “indexed”, `awaiting_approval` already means “has markdown”). `source_materials.subtopic_id` is NOT NULL today, so topic intake needs an XOR like quizzes. Admin ingest, student directory, and seeded per-subtopic catalogs must keep working. Worker must not auto-publish. No LangGraph, no new `IngestTargetKind` that still points at SMV, no second student-visibility table.

## Usage (caller's view)

A teacher calls `submit_pdf` on a **topic** and polls `get_run` until `outline_review` or `failed`. HITL 1 is `patch_outline` (replace the run-local DAG) then `accept_outline` (quotas + match-or-create curriculum rows). There is no generate HTTP: accept is the resume. Slice 1 parks at `generating` without item jobs. Later, the same `get_run` grows a QA table; `publish` writes the student copies. Call sites: teacher inbox (`/teacher/generation`), ingest hook `on_intake_indexed` plus `generation_jobs` in the same worker process, thin `/teaching/topics/{id}/generation-runs*`. Deprecated POST `/teaching/subtopics/{id}/lesson-proposals` resolves the parent topic. Admin still POSTs `/admin/subtopics/{id}/materials`. Full README: `usage.md`.

## Shape

**`GenerationRun` is the workflow aggregate.** Phase, outline, later draft markdown, later draft quiz version, and FKs to the intake version / published copies all hang off `content_generation_runs`. Teachers poll `run_id`. Intake PDF is a topic-scoped parent `slug="source"` that Docling takes to **READY** and leaves unpublished. Outline nodes are `content_generation_outline_nodes` until accept, then match-or-create `Subtopic` + `LearningOutcome`. Student `slug="lesson"` SMV and released `topic_mastery` exist only after HITL 2.

Orchestration splits by **kind of work**, not by a new ingest target: `ingest_jobs` stay “parse this SMV”; `generation_jobs` (SKIP LOCKED, same worker, ingest first) own outline and later LLM. After READY, `on_intake_indexed` is a no-op for admin and, for a run in `indexing`, enqueues `kind=outline` in the **same commit**. That kills `complete_from_chunks`. `IngestTargetKind` does not grow.

Public HTTP is five calls in slice 1 (`submit`, `get`, `list`, `patch`, `accept`). PATCH replaces the outline document rather than exposing merge/drop/recompute opcodes. Quotas are **derived** via Largest Remainder on GET until accept **freezes** integers (single source of truth). `ItemCount` encodes 60–80. Failed is terminal for the in-flight unique so slice 1 needs no discard to unblock a retry-by-resubmit.

Interface depth: those five operations hide blob storage, XOR parent, in-flight lock, Docling, outline LLM/heuristic, heading cluster, slug/name match, Largest Remainder, and curriculum writes. Exposed on purpose: async poll (`RunPhase`) and the outline document (that *is* HITL 1). Per boundary-discipline, `UploadFile` and LLM JSON parse behind the interface. Per encode-lessons-in-structure, illegal phases are unrepresentable on `GenerationRun` and draft subtopics cannot exist as the review payload. Per make-operations-idempotent, re-accept after freeze returns the current run. Per separate-before-serializing-shared-state, concurrent submits lose on the partial unique, not a lock service.

**Red-flag screen:** not shallow — caller does not orchestrate index-then-outline-then-quotas. Not leakage — jobs, SMV statuses, and Instructor schemas stay private; wire types stay in `schemas.py`. Not temporal decomposition — one `generation` module owns the run across ingest time, HITL 1, later gen, and publish; `outline.py` is pure math/parse, not a phase service. Not a pass-through — `submit_pdf` authorizes, locks, mints the run, then queues; `queue_topic_intake_pdf` is a sibling of admin enqueue, not `queue_source_material_pdf(..., topic_id=optional)`.

## Synthesis decision

Filled by arena synthesis; this is candidate-1.

## Tradeoffs accepted

- We accept a run table that is never student-visible in exchange for not stretching SMV into a second “is this the lesson?” switch. Publish copies into the tables students already read.
- We accept `generation_jobs` in slice 1 (outline only) in exchange for keeping `ingest_jobs` index-only. Outline LLM does not ride Docling failure/success, and retry of outline will not re-parse the PDF.
- We accept parking at `generating` with zero jobs in slice 1 in exchange for a stable `accept_outline` signature when slice 2 starts enqueueing.
- We accept failed runs as terminal (new submit allowed) in exchange for no discard/retry HTTP in slice 1. Teachers re-upload after outline failure.
- We accept a heading-skeleton outline when OpenRouter is missing in exchange for a demoable HITL 1. Garbage DAG is still editable; we do not fail the indexed PDF.
- We accept JSON `proposed_outcomes` on the node in exchange for not creating an outcomes child table for 1–3 draft strings.
- We accept flat `subtopics` (no `parent_subtopic_id`) in exchange for not migrating seeded trees. DAG lives on the run.
- We accept topic-scoped chunks as teacher+admin forever in this phase in exchange for not using `submitted_by_user_id` as a pipeline flag.
- We accept leaving `awaiting_approval` in the SMV enum (unused by this flow) in exchange for not rewriting leftover CHECKs in the same Alembic as XOR.
- We accept 410 on old proposal GET/LIST in exchange for not keeping `proposal_id == version.id` as a public identity.

## Alternatives considered

**Stretch `SourceMaterialVersion` (slug `"lesson"`, `awaiting_approval`, `id` is the poll key).** Rejected. Interface looks small (one id) but leaks the wrong grain: callers would still need an outline resource, an item bank, and a topic vs leaf distinction that the version row cannot name. `READY`+markdown as review collides with admin “indexed”. This is the shape product just left. Interface depth is fake — the complexity sits in status mapping the UI must relearn.

**Curriculum-rows-as-workflow (draft `Subtopic` / `LearningOutcome` rows are the HITL document).** Rejected. Discarded runs pollute the academic tree; student directory and unique `(topic, slug)` start seeing work-in-progress; accept becomes “please don’t delete.” Callers must know which subtopics are real. The run-local node table hides that; curriculum writes happen once, on accept.

**Hang outline LLM off `ingest_jobs` after READY (`complete_from_chunks` 2.0), defer `generation_jobs` to slice 2.** Rejected. It keeps the SMV-adjacent pattern: ingest target kind stays SMV but the job’s meaning becomes “index and also generate.” Failure modes mix. Admin ingest grows a “is this a run?” branch in the hot path instead of a no-op hook. Shallower module: ingest callers learn generation policy.

**New `IngestTargetKind` pointing at the SMV or the run.** Rejected. `target_kind` is which table `target_id` points at. A new kind that still points at `source_material_versions` is an extra public switch for the same row. A kind pointing at `content_generation_runs` makes ingest parse a run id it cannot chunk.

**LangGraph checkpointer as orchestrator.** Rejected. Policy assistant already has a graph; this pipeline’s checkpoint is the run row + claim tables. A second orchestrator is two sources of “what phase is it?”

**`lesson_drafts` (or equivalent) as the student-visibility switch.** Rejected again for **student** reads. A run table is allowed because nothing student-facing reads it until publish copies into published SMV / released quiz.

**Opcode PATCH (`merge_nodes`, `drop_node`, `recompute_quotas`).** Rejected. Callers would coordinate several methods to finish HITL 1 (shallow). One document replacement hides drop/merge as omitted ids + folded weights.

## Open questions and risks

- Should outline failure offer `retry` on the same run (re-enqueue `kind=outline`, keep the READY PDF) in slice 1 after all, or is re-upload acceptable until slice 4 discard exists?
- When two remainder ties occur, is original-sequence tie-break the product rule, or should the research’s “Alpha and Gamma each get one” be encoded as a named sort (remainder desc, then sequence)?
- On match, this sketch refuses to rewrite seeded subtopic name/sequence. If the teacher renames a matched node, should accept update the curriculum row?
- `on_intake_indexed` in the READY commit still loses if the process dies after the earlier `RUNNING` commit and before READY (existing stuck-job problem). Do we sweep `indexing`+READY runs at poll start?
- Directory unlock for generated topics is slice 4. If someone publishes via a future path before directory ships, students would have a released topic quiz still gated on subtopic passes — should publish be blocked on that directory branch?
- Dual-role users remain unrestricted admins. Is that still correct when generation writes curriculum rows?

## Next implementation step

Alembic for `content_generation_runs`, `content_generation_outline_nodes`, `generation_jobs`, and `source_materials` topic XOR; then `submit_pdf` + ingest hook that enqueues outline, with `complete_from_chunks` deleted.

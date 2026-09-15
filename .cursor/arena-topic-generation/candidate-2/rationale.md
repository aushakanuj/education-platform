# Rationale

## Problem

Teacher PDF intake must become topic-grain content generation: index-only ingest, two HITL interrupts (draft curriculum, then QA of one topic lesson plus 60–80 tagged items), publish of a topic lesson and a `topic_mastery` quiz. The landed v1 (`LessonProposal` = `SourceMaterialVersion` on subtopic slug `lesson`, `complete_from_chunks`, `awaiting_approval`) is the wrong grain and the wrong review badge. Constraints that stay: admin ingest terminal is `READY` (indexed, unpublished, no generation); the worker never publishes; `IngestTargetKind` names a table not a pipeline; student reads stay published/released with keys off those paths; `Question.subtopic_id` and outcome tags are required; in-flight teacher work must not block admin index on a leaf; no Redis/Kafka/MinIO/LangGraph for this flow; seeded per-subtopic catalog remains for topics without a published topic lesson. The non-obvious part is how to own two interrupts, uniqueness, failure, and discarded outlines **without** a `content_generation_runs` row — because a run table would be a second curriculum tree (outline nodes) plus a second visibility story until copy-out, while the product already has a topic tree and topic-scoped materials.

## Usage (caller's view)

Callers address the **topic**. They submit a PDF, poll `GET .../topics/{id}/generation`, edit and accept a draft tree, then (later slices) QA and publish. They never receive a run id. The deprecated subtopic `lesson-proposals` POST is an alias onto the parent topic. The worker claims the same `ingest_jobs` loop; after `READY` it may enqueue another job against the same `source_material_version_id` with `phase=outline` (then `items` / `lesson`). Full README, HTTP, and three call sites: [usage.md](usage.md). Types in [shape.md](shape.md) are derived from that usage.

## Shape

The workflow **is** the curriculum graph plus a topic-scoped `SourceMaterialVersion`. Topic XOR on `source_materials`: slug `source` is the intake hangar (mutex `open_intake_version_id`, `target_item_count`); slug `lesson` is the one unpublished-then-published study object. HITL 1 writes `subtopic_revisions` / `learning_outcome_revisions` keyed by the intake version — weights and quotas live on those rows. Accept promotes match-or-create live `Subtopic` / `LearningOutcome`. Jobs keep `target_kind=source_material_version` and gain a phase; no pipeline kind. Phase on the snapshot is **derived** from lock, versions, revision status, and jobs (derive-instead-of-sync). Intake failure is the only path that marks the PDF `FAILED`; outline/items/lesson failures fail the job (and the lesson version when that is the artifact) so `READY` still means indexed. Discard flips proposed revisions to `discarded` and clears the hangar lock; live subtopics were never inserted. Abandon after accept keeps live subtopics and archives unpublished products.

In-flight uniqueness without a run id: compare-and-set `open_intake_version_id` (409 if held). That lock spans indexing through QA because `READY` is not “generation finished.” Failed generations without a run id: `failure_reason` on the snapshot is the failed job (or intake/lesson version) for the current derived phase; retry re-enqueues against the same version id. Discarded outlines without a run id: revision status + lock null; PDF remains `READY` for `reopen`.

Public surface hides mutex CAS, Largest Remainder, hybrid match, job phase, and derive_phase. Callers see topic-scoped verbs. ORM and `IngestJob` are not exported (boundary-discipline). One module (`topic_generation`) owns the rules so index/outline/accept are not three packages repeating “is this generation open?” (avoid temporal decomposition). Router is not a pass-through of job fields; it parses wire types and calls the service.

Interface depth: a small topic-shaped API concentrates lock, draft-tree, and later item/lesson policy. A run-shaped API would look smaller on day one (`GET /runs/{id}`) and then force every caller to learn run vs topic vs published SMV.

## Synthesis decision

Filled by arena synthesis; this is candidate-2.

## Tradeoffs accepted

- We accept a mutex column on the topic `source` hangar in exchange for not inventing a run aggregate whose only job is “is this topic busy, and which PDF?”
- We accept derived phase (a function that can be wrong if we forget a fact) in exchange for not storing a phase enum that drifts from the tree and the jobs.
- We accept a `subtopic_revisions` sibling in exchange for keeping live `Subtopic` uniqueness intact and making discard a status flip instead of deleting half-created curriculum (or weakening unique constraints with a `draft` flag on `subtopics`).
- We accept overloading `ingest_jobs` with outline/items/lesson phases in exchange for one claim loop and no `IngestTargetKind` that still points at `source_material_versions`. The table name stays “ingest”; the phase says what to do.
- We accept that accept is a real curriculum commit (abandon does not un-create subtopics) in exchange for HITL 1 meaning “this is the topic tree,” not “a sandbox document we might throw away after tagging 80 items.”
- We accept listing history as intake versions, not runs, in exchange for provenance arrows (`generated_from_version_id`) instead of an aggregate root.
- We accept empty lesson DRAFT on accept (slice 1) in exchange for a hangar that later jobs can write without a run pointing at “the draft markdown blob.”

## Alternatives considered

- **`content_generation_runs` + outline_nodes (the product-plan default).** Callers get a run id, stored phase, failure_reason, and FKs to intake/lesson/quiz. That hides job mechanics behind a new aggregate, but it **exposes** a second identity every UI and worker must thread, and it **duplicates** the topic tree as `outline_nodes` until accept copies it into `Subtopic`. Interface looks tidy (`GET /runs/{id}`) while leaking “run vs curriculum vs published SMV” into every caller. Lost for this shape: the draft tree is the curriculum; the hangar lock is the busy bit; a run is a document the teacher should not be editing.
- **Stretch intake `SourceMaterialVersion` as the workflow (v1 LessonProposal, `awaiting_approval`, markdown-as-review).** One id, short call chain, already in the repo. It hides nothing that matters here: no outline, no 80-item bank, `READY` vs review collision, subtopic grain. Lost because grounding forbids stretching SMV into that state machine and forbids `READY`+markdown as review.
- **Draft status on live `Subtopic` / `LearningOutcome` (no sibling).** Teacher really is “editing the topic tree.” It hides the sibling table, but it **exposes** uniqueness and sequence fights with seeded live rows, and discard becomes delete-or-weaken-constraints. Lost: hybrid match needs a proposed node beside an existing live subtopic; a sibling encodes that without a run and without polluting `uq_subtopics_topic_slug`.
- **`generation_jobs` table beside ingest.** Cleaner names, same SKIP LOCKED pattern. Exposes a second claim loop and a second worker vocabulary for work that is still “do something to this SMV.” Lost: assigned shape extends ingest phases; `target_kind` stays which table.

## Open questions and risks

- Should `reopen` of a READY intake after discard be in slice 1, or is re-upload enough until a teacher actually needs it?
- After accept, if the teacher hates the live subtopics they just promoted, is the recovery path “manual curriculum edit” or do we need a guarded un-accept that we explicitly refused here?
- Derived `failed` vs `outlining` when an outline job fails after writing a partial tree: is “replace on retry” enough, or should a failed outline always wipe `proposed` rows so GET cannot look like `outline_review`?
- Directory unlock: product text says generated topics unlock the topic quiz when the **lesson is published**. Should that also require the student to complete the topic lesson (mirroring subtopic “complete the lesson first”), and if so in which slice?
- Coexistence: a topic with seeded subtopic lessons **and** a published generated topic lesson — does the directory show both, or does the published topic lesson hide leaf lessons? The sketch unlocks the topic quiz from the topic lesson and leaves leaf rows in place; is that the catalog we want?
- `ingest_jobs.phase` for long LLM work in the same process as Docling: is POC-sized load acceptable, or will ITEMS starve INDEX? (No Redis in this design; this is a capacity question, not a new queue product.)

## Next implementation step

Alembic: topic XOR on `source_materials`, hangar `open_intake_version_id` + `target_item_count`, `subtopic_revisions` / `learning_outcome_revisions`, `ingest_jobs.phase`; then topic submit → INDEX → READY → OUTLINE → snapshot/PATCH/accept/discard with the 409 lock, leaving ITEMS/LESSON/QA as `not implemented`.

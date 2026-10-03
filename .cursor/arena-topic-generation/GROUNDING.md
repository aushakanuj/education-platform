# Grounding: topic-grain content generation (architect Phase A)

Traced 2026-09-09 from how-explorers + why archaeology. This is the constraint set for design sketches. Do not treat the current LessonProposal as the destination.

## What exists (runtime)

Teacher PDF intake is unreleased. HTTP: `POST /api/v1/teaching/subtopics/{id}/lesson-proposals` (202), GET by version id, LIST by subtopic. No approve/discard/retry. No frontend.

`LessonProposal` is **not a table**. `id == SourceMaterialVersion.id`. Marker: `submitted_by_user_id IS NOT NULL`. Always on `SourceMaterial.slug == "lesson"` under a **required** `subtopic_id`. Admin index uses the same enqueue (`queue_source_material_pdf`) with submitter null.

Worker (`ingest_jobs` claim, Docling HybridChunker, pgvector): after chunks, if submitter set → `complete_from_chunks` writes slide markdown onto **that same PDF version**, status `awaiting_approval`, optional 5-question **DRAFT** `subtopic_mastery` quiz. If submitter null → `READY`, no markdown. Worker **never** writes `published`.

Student catalog: `published_material_version` = max published version under the subtopic (no slug filter) + non-empty markdown on GET. Quizzes: latest `QuizVersion.RELEASED` only. Directory topic quiz unlocks after every **available** subtopic quiz has a pass. Seeded topic quiz concatenates subtopic items; `Question.subtopic_id` is still required.

Auth: teacher/admin + `taught_offering_ids` (section ignored). Students 403 on proposal routes. No new grant types.

## Why the current stretch exists (do not re-litigate the 09:00 arena)

Same-morning arena (candidate-2 base, [Skill for new ideas](c972ae52-8c0d-4c8b-a376-e6221f6ec8bc)): persist on SMV because student visibility already lives there; reject `lesson_drafts` as a second “is this student-visible?” table; reject `READY`+markdown as review (admin badge already means indexed); reject `IngestTargetKind.LESSON_DRAFT` (`target_kind` is which table `target_id` points at).

That v1 assumed **one lesson per subtopic**, ~5 questions, one approve. Product later the same day: research doc is the destination; **topic grain**; two HITL interrupts; 60–80 tagged items; one topic lesson; do not stretch SMV as the workflow aggregate.

## Preserve

- Admin ingest terminal is `READY` = indexed, unpublished, no generation. Do not overload as awaiting review.
- Worker never auto-publishes. Students see only `published` ∧ markdown / `released` quiz.
- `IngestTargetKind` stays “which table,” not which pipeline.
- In-flight teacher work must not block admin index on the same curriculum leaf.
- Proposal/intake PDF chunks: `required_roles` teacher+admin until a later explicit student-index decision.
- Access = roles + teaching assignments / enrollments. No new grants.
- Thin HTTP; logic in module services. Python/`uv` only.
- No Redis/Kafka, OpenSearch/Chroma, MinIO, second generative microservice, LangGraph for this flow (policy assistant keeps LangGraph).
- `Question.subtopic_id` + `question_outcome_tags` required on every generated item. Answer keys never on student query paths. Teacher-only rationales belong on `question_answer_keys` (already “do not join from student paths”).
- Existing `QuizScope.TOPIC_MASTERY` XOR `SUBTOPIC_MASTERY`. Seeded per-subtopic catalog stays for topics without a published generation run.
- Docling HybridChunker + `section_heading` + token_count + pgvector stay as index.

## Change

- Workflow owner is **topic grain**, not teacher-picked `subtopic_id`.
- Generated study object: **one topic lesson**. Subtopics are diagnostic tags (outline HITL, then item tags), not generated student lessons.
- Two HITL: (1) outline + weights/quotas before expensive gen; (2) QA of lesson + item table before publish.
- Intake PDF version ends **READY** (index-only), even for teachers. Review state lives on the run, not `awaiting_approval`.
- Publish writes topic-scoped published material + **releases** `topic_mastery` quiz. Items keep `subtopic_id`. Do not also emit `subtopic_mastery` quizzes from this pipeline.
- Landed `POST .../subtopics/{id}/lesson-proposals` may remain as **intake alias** onto the parent topic; it is not the product destination.

## Avoid

- Stretching `SourceMaterialVersion` on slug `"lesson"` as the generation state machine (outline, 80 items, two interrupts, topic vs leaf).
- `READY` + markdown as “please review.”
- New `IngestTargetKind` values that still point at `source_material_versions`.
- A second table that is another student-visibility switch (the old `lesson_drafts` rejection still holds for **student** reads). A run table that is never student-visible until publish copies into published SMV / released quiz is a different thing.
- LangGraph checkpointer as a second orchestrator beside `ingest_jobs`.
- Analytics dashboards in this design (only make them possible).
- Auto-creating `Subtopic` rows before outline accept.

## Load-bearing schema facts

- `source_materials.subtopic_id` is NOT NULL. Topic-scoped material needs XOR like quizzes.
- One `CommonMasteryQuiz` per topic (`uq_common_mastery_quizzes_topic`).
- `published_material_version` is subtopic-scoped today; topic lesson needs a parallel lookup.
- `awaiting_approval` occupies the proposal in-flight unique and requires markdown. New flow must not use it as outline_review.
- Directory overall-quiz gate is “pass all subtopic quizzes.” Generated topics have no those quizzes; unlock must branch on published topic lesson + released topic quiz.

## Callers to keep working

- Admin `POST /admin/subtopics/{id}/materials` → READY.
- Student `GET /me/learning-directory`, `GET /subtopics/{id}/material`, quiz start (keys omitted).
- Seeded `approved_materials` topic with per-subtopic lessons/quizzes.

## First slice after sketch (product plan)

Outline HITL only: schema + topic enqueue + index-then-outline + PATCH/accept. No 60–80 gen, no topic lesson, no QA publish, no teacher UI.

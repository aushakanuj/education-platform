# Topic generation (no run table)

A teacher uploads a PDF **against a topic**. The PDF is indexed like an admin ingest (terminal `READY`, unpublished). The teacher then edits a **draft curriculum tree** for that topic — proposed subtopics, outcomes, weights, quotas — not a generation-run document. Accept **promotes** those drafts into live `Subtopic` / `LearningOutcome` rows. Later, DRAFT questions are tagged with those subtopics, and one unpublished topic lesson waits for QA. Publish writes the student-visible topic lesson and releases a `topic_mastery` quiz.

There is no `content_generation_runs` row and no run id. Callers address **the topic**. The open generation is “whatever intake is locked on this topic’s `source` material.” History is the list of intake versions.

Students still see only `published` material with markdown and `released` quizzes. Admin ingest still ends at `READY` with a null submitter and never generates.

## Quickstart

```text
Teacher JWT
  POST /api/v1/teaching/topics/{topic_id}/source-materials
       multipart: title, file, optional target_item_count (60–80, default 80)
       → 202 { topic_id, intake_version_id, phase: "indexing" }

  GET  /api/v1/teaching/topics/{topic_id}/generation
       poll until phase is outline_review | failed | …
       payload is a TopicGenerationSnapshot: derived phase, draft tree, job error

  PATCH /api/v1/teaching/topics/{topic_id}/outline
       edit titles, merge/drop, retarget to an existing subtopic, weights
       quotas are recomputed (Largest Remainder) from weights × target_item_count

  POST /api/v1/teaching/topics/{topic_id}/outline/accept
       match-or-create live Subtopic + LearningOutcome; lock stays
       creates an empty unpublished topic `lesson` version

  POST /api/v1/teaching/topics/{topic_id}/outline/discard
       draft tree discarded; live curriculum untouched; lock cleared
       intake PDF stays READY (index is still valid)

  POST /api/v1/teaching/topics/{topic_id}/generation/retry
       re-enqueues the failed phase against the same intake_version_id

  POST /api/v1/teaching/topics/{topic_id}/generation/abandon
       after accept, before publish: archive draft lesson + DRAFT items;
       live Subtopics stay; lock cleared

  GET  /api/v1/teaching/topics/{topic_id}/qa
       HITL 2: lesson markdown + item table with keys (teacher only)

  POST /api/v1/teaching/topics/{topic_id}/qa/items/reject
       drop flagged DRAFT items; fill quota again

  POST /api/v1/teaching/topics/{topic_id}/publish
       topic lesson → published; topic_mastery quiz → released; lock cleared

  GET  /api/v1/teaching/topics/{topic_id}/intakes
       past source PDF versions (no run list)

  POST /api/v1/teaching/topics/{topic_id}/intakes/{intake_version_id}/reopen
       idle topic, READY teacher PDF: take the lock again, rewrite a draft tree
```

Deprecated intake alias (not the product destination):

```text
POST /api/v1/teaching/subtopics/{subtopic_id}/lesson-proposals
     → same 202 snapshot for the parent topic
     does not pin the generated lesson to that subtopic
```

Auth is unchanged: `scoped("teaching.generation")` (or the existing teaching scope), `taught_offering_ids` for teachers, unrestricted administrators. Students 403. No new grant types.

`GET /subtopics/{id}/material` stays subtopic-published. Generated study grain is `GET /topics/{id}/material` (slice 4) plus a directory field for the published topic lesson.

## What the worker does (not an HTTP caller)

Same process: `uv run python -m education_platform.workers` claims `ingest_jobs` with `FOR UPDATE SKIP LOCKED`.

Jobs are still `target_kind=source_material_version`. `target_id` is always a `SourceMaterialVersion.id`. A **phase** column says what to do to that version (`index` | `outline` | `items` | `lesson`). There is no `IngestTargetKind` that means “pipeline,” and no `generation_jobs` table.

```text
INDEX   teacher topic `source` PDF → Docling + HybridChunker + pgvector → READY
        then enqueue OUTLINE for the same version id
        admin / null submitter: INDEX only, stop at READY (today)

OUTLINE headings + token mass → proposed subtopic_revisions (HITL 1)

ITEMS   after accept: DRAFT questions tagged with live subtopic_id + outcomes
        keyed by the same intake version id (provenance, not a run)

LESSON  markdown (+ Mermaid retry) onto the topic-scoped `lesson` version
        that version stays unpublished until POST publish
```

The worker never writes `published` / `released`. Intake `READY` is index-only: no markdown, not a review badge.

## In-flight, failure, discard (no run id)

**In-flight uniqueness.** The topic-scoped `SourceMaterial` with slug `source` holds `open_intake_version_id`. Submit compare-and-sets that FK from null; if it is already set, HTTP 409. That is the generation mutex. After index, the PDF is `READY` — uniqueness does **not** live on `processing|awaiting_approval`. `awaiting_approval` is not used.

**Failed generations.** Failure hangs on the artifact that actually failed, plus the job row:

| Phase   | Intake SMV     | Lesson SMV        | Lock | Retry |
| ------- | -------------- | ----------------- | ---- | ----- |
| index   | `FAILED`       | —                 | held | same version, re-INDEX |
| outline | stays `READY`  | —                 | held | re-OUTLINE (replace proposed rows) |
| items   | stays `READY`  | unpublished       | held | re-ITEMS |
| lesson  | stays `READY`  | `FAILED`          | held | re-LESSON |

Do not flip a successfully indexed PDF to `FAILED` because the LLM outline died. Snapshot `failure_reason` is the failed job’s error when the derived phase is `failed`.

**Discarded outlines.** `discard_outline` marks that intake’s `subtopic_revisions` / outcome drafts `discarded`, cancels leftover jobs (worker no-ops if the lock no longer points at them), and clears `open_intake_version_id`. Live `Subtopic` rows are unchanged because they were never written. The PDF remains `READY` so the teacher can `reopen` it or upload a new file. After accept, discard is the wrong verb: use `abandon` — curriculum stays, unpublished lesson and DRAFT items go away, lock clears.

## Call site 1 — teacher page

`/teacher/topics/:topicId/generate` is the destination. The unreleased lesson-proposal UI is not the product. Poll the **topic**, not a run id.

```tsx
// frontend/src/pages/teacher/TopicGenerationPage.tsx
import {
  acceptOutline,
  discardOutline,
  fetchGeneration,
  patchOutline,
  publishTopicGeneration,
  submitTopicSource,
  type TopicGenerationSnapshot,
} from "../../api/teachingGeneration";

async function onUpload(topicId: string, file: File) {
  const accepted = await submitTopicSource(topicId, file, {
    title: "Unit 4 source pack",
    target_item_count: 80,
  });
  // accepted.phase === "indexing"; poll the topic
  let current = await fetchGeneration(topicId);
  while (current.phase === "indexing" || current.phase === "outlining") {
    await sleep(1500);
    current = await fetchGeneration(topicId);
  }
  // outline_review | failed
}

async function onAccept(snapshot: TopicGenerationSnapshot) {
  await acceptOutline(snapshot.topic_id);
  // live subtopics now exist; students still see nothing new
}

async function onDiscard(topicId: string) {
  await discardOutline(topicId);
  // lock cleared; seeded catalog unchanged
}

async function onPublish(topicId: string) {
  await publishTopicGeneration(topicId);
  // student topic lesson + topic_mastery quiz
}
```

Chrome: one status badge from `snapshot.phase`. Never map `READY` (admin ingest) onto outline review or QA. Outline editor is a tree of `snapshot.outline` nodes (revision ids), not a JSON blob on a run.

## Call site 2 — thin HTTP router

```python
# modules/topic_generation/router.py
@router.post(
    "/teaching/topics/{topic_id}/source-materials",
    response_model=GenerationAcceptedOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit(
    topic_id: UUID,
    title: str = Form(...),
    file: UploadFile = File(...),
    target_item_count: int = Form(80),
    request: ScopedRequest = Depends(scoped("teaching.generation.submit")),
) -> GenerationAcceptedOut:
    snapshot = await service.submit_source_pdf(
        request.session,
        request.scope,
        request.principal,
        topic_id=topic_id,
        title=title,
        file=file,
        target_item_count=target_item_count,
    )
    await request.record_rows(1, detail=f"intake={snapshot.intake_version_id}")
    return GenerationAcceptedOut.from_snapshot(snapshot)


@router.get("/teaching/topics/{topic_id}/generation", response_model=GenerationOut)
async def get_generation(
    topic_id: UUID,
    request: ScopedRequest = Depends(scoped("teaching.generation.get")),
) -> GenerationOut:
    snapshot = await service.generation_snapshot(
        request.session, request.scope, topic_id
    )
    return GenerationOut.from_snapshot(snapshot)
```

The router does not mention jobs, phases-as-storage, or revision tables. It does not accept a `run_id`.

Deprecated alias: resolve `Subtopic.topic_id`, call `submit_source_pdf`. Do not keep `LessonProposal` as the return type.

## Call site 3 — worker dispatch and student directory

```python
# workers/ingest.py — same claim loop, phase on the job
if job.phase is IngestJobPhase.INDEX:
    index_source_pdf(...)  # existing Docling path; intake → READY
    maybe_enqueue_outline(session, version)  # teacher + topic slug source only
elif job.phase is IngestJobPhase.OUTLINE:
    topic_generation.jobs.write_outline(session, job.target_id)
elif job.phase is IngestJobPhase.ITEMS:
    topic_generation.jobs.write_items(session, job.target_id)
elif job.phase is IngestJobPhase.LESSON:
    topic_generation.jobs.write_lesson(session, job.target_id)
```

`complete_from_chunks` is gone. Index failure may mark the intake version `FAILED`. Outline / items / lesson failure must **not**.

Student directory (keep seeded topics working):

```python
# academics/directory.py
topic_lesson = await published_topic_material_version(session, topic.id)
if topic_lesson is not None:
    overall_unlocked = True  # generated topic: lesson published, not "pass every subtopic quiz"
else:
    overall_unlocked = bool(quiz_nodes) and all(
        node.quiz is not None and node.quiz.passed for node in quiz_nodes
    )
```

`GET /topics/{id}/material` reads that published topic lesson. Answer keys stay off student query paths.

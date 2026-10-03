# Topic generation runs

A teacher (or unrestricted administrator) submits a PDF **on a topic**. That mint a `GenerationRun`. The run is the only object the UI polls. The PDF becomes a topic-scoped `SourceMaterialVersion` that Docling indexes to **READY** and then forgets. Outline, later items, later lesson, and both human gates live on the run. Students see nothing until HITL 2 publish copies a topic lesson + released `topic_mastery` quiz into the existing student tables.

Callers import `education_platform.modules.generation.service` (HTTP) or `education_platform.modules.generation.worker` (same worker process as ingest). They never import `IngestJob`, `GenerationJob`, `SourceMaterialVersionStatus`, or RAG wire schemas.

`LessonProposal` / `ProposalPhase` / `complete_from_chunks` go away. The unreleased `/teaching/subtopics/{id}/lesson-proposals` POST remains as a **deprecated intake alias** that resolves the parent topic and starts a topic run.

## Quickstart (slice 1 — outline HITL)

```python
from education_platform.modules.generation.service import (
    accept_outline,
    get_run,
    list_runs,
    patch_outline,
    submit_pdf,
)

# 1. Enqueue. 202. Phase is indexing. Returns a run id to poll — not an SMV id.
accepted = await submit_pdf(
    session, scope, principal,
    topic_id=topic_id, title=title, file=upload,
    target_item_count=80,  # optional; clamped 60–80, default 80
)

# 2. Poll until outline_review or failed.
run = await get_run(session, scope, accepted.run_id)
# indexing  = ingest_jobs still owns the PDF (Docling + embeddings)
# outlining = generation_jobs kind=outline owns the LLM/heuristic DAG
# outline_review = nodes are on the run; teacher may PATCH
# failed = ingest or outline blew up; intake PDF may already be READY

# 3. HITL 1. Replace the outline document (titles, DAG, weights, match/create).
#    GET already shows preview quotas via Largest Remainder. PATCH does not
#    write Subtopic rows.
run = await patch_outline(session, scope, accepted.run_id, outline_patch)

# 4. Accept freezes integer quotas, match-or-creates Subtopic + LearningOutcome
#    stubs, stamps each node with accepted_subtopic_id, moves phase to generating.
#    Slice 1 does **not** enqueue item/lesson jobs. Same signature in slice 2
#    starts to enqueue them; callers do not change.
run = await accept_outline(session, scope, principal, accepted.run_id)
```

`list_runs(session, scope, topic_id)` is the inbox for that topic (in-flight first, then newest). The live student lesson is not in this list; it stays on `GET /subtopics/{id}/material` until slice 4 adds `GET /topics/{id}/material`.

## What the caller does not do

- Does not POST `/admin/subtopics/{id}/materials` for this flow. That path stays administrator **index-only**, subtopic-scoped, `submitted_by_user_id IS NULL`, READY, no outline, no run.
- Does not pick a `subtopic_id` as the home of the generated lesson. Subtopics are diagnostic tags after accept, not student lessons.
- Does not set `lifecycle_status=published` or `awaiting_approval`, and does not write `content_markdown` onto the intake PDF.
- Does not poll `ingest_jobs` or `generation_jobs`. `RunPhase` is the only status the UI needs.
- Does not insert `Subtopic` / `LearningOutcome` while drafting. Discarded and failed runs must not pollute curriculum.
- Does not call authoring `generate` / `publish_draft` to get a student-visible quiz. Publish (slice 4) releases `topic_mastery` only.
- Does not coordinate a second "please generate the outline" HTTP call after READY. Index success enqueues outline inside the worker.

---

## Call site 1 — teacher outline inbox (slice 5 UI; HTTP is slice 1)

New rail `/teacher/generation`. Topic picker from taught offerings. Upload + poll copied from admin ingest chrome, pointed at generation HTTP. Outline editor is a tree + weight fields, not a markdown preview.

```ts
// frontend/src/api/generation.ts  (new)
import { apiRequest } from "./client";
import type {
  AcceptedRun,
  GenerationRun,
  OutlinePatch,
} from "./generationTypes";

export async function submitTopicPdf(
  topicId: string,
  file: File,
  title: string,
  targetItemCount?: number,
): Promise<AcceptedRun> {
  const body = new FormData();
  body.append("file", file);
  body.append("title", title);
  if (targetItemCount != null) {
    body.append("target_item_count", String(targetItemCount));
  }
  return apiRequest<AcceptedRun>(
    `/teaching/topics/${encodeURIComponent(topicId)}/generation-runs`,
    { method: "POST", body },
  );
}

export async function getGenerationRun(runId: string): Promise<GenerationRun> {
  return apiRequest<GenerationRun>(
    `/teaching/generation-runs/${encodeURIComponent(runId)}`,
  );
}

export async function listGenerationRuns(topicId: string): Promise<GenerationRun[]> {
  return apiRequest<GenerationRun[]>(
    `/teaching/topics/${encodeURIComponent(topicId)}/generation-runs`,
  );
}

export async function patchOutline(
  runId: string,
  patch: OutlinePatch,
): Promise<GenerationRun> {
  return apiRequest<GenerationRun>(
    `/teaching/generation-runs/${encodeURIComponent(runId)}/outline`,
    { method: "PATCH", body: JSON.stringify(patch) },
  );
}

export async function acceptOutline(runId: string): Promise<GenerationRun> {
  return apiRequest<GenerationRun>(
    `/teaching/generation-runs/${encodeURIComponent(runId)}/accept-outline`,
    { method: "POST" },
  );
}

const HITL1_TERMINAL = new Set(["outline_review", "failed", "discarded", "published"]);

export async function pollUntilOutline(
  runId: string,
  signal?: AbortSignal,
): Promise<GenerationRun> {
  for (;;) {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    const run = await getGenerationRun(runId);
    if (HITL1_TERMINAL.has(run.phase)) return run;
    await new Promise((r) => setTimeout(r, 1500));
  }
}
```

```tsx
// frontend/src/pages/teacher/GenerationRunsPage.tsx  (excerpt, slice 5)
async function onUpload(topicId: string, file: File) {
  const accepted = await submitTopicPdf(
    topicId,
    file,
    file.name.replace(/\.pdf$/i, ""),
  );
  const run = await pollUntilOutline(accepted.run_id, abort.signal);
  if (run.phase === "failed") {
    setError(run.failure_reason ?? "Generation failed");
    return;
  }
  setSelected(run); // run.outline.nodes + preview quotas
}

async function onSaveOutline(runId: string, patch: OutlinePatch) {
  setSelected(await patchOutline(runId, patch));
}

async function onAccept(runId: string) {
  const run = await acceptOutline(runId);
  setNote(
    `Accepted ${run.outline.nodes.length} subtopics. Item generation is not in this slice.`,
  );
}
```

Deprecated alias used only if an old client still posts to a subtopic:

```ts
// POST /teaching/subtopics/{subtopicId}/lesson-proposals
// same FormData; response is AcceptedRun { run_id, topic_id, phase: "indexing" }
// GET/LIST on lesson-proposals are 410 Gone.
```

`SubjectMaterialsPage` stays a read-only view of **published** student lessons. A teacher who wants to see what students see still opens the directory after slice-4 publish.

---

## Call site 2 — worker (same process, two claim tables)

Admin index jobs are unchanged: `IngestTargetKind.SOURCE_MATERIAL_VERSION`, READY, no markdown, no run. **No new `IngestTargetKind`.** After a source version reaches READY, the ingest worker asks generation whether that version is someone's intake.

```python
# backend/src/education_platform/workers/ingest.py  (hook, not a new target kind)

from education_platform.modules.generation.worker import on_intake_indexed

def _process_source_material(session, job, parse, ...):
    # ... existing Docling, chunk, embed ...
    version.lifecycle_status = SourceMaterialVersionStatus.READY
    version.failure_reason = None
    # Admin path: on_intake_indexed is a no-op (no run points at this version).
    # Teacher topic intake: same commit as READY inserts generation_jobs(kind=outline)
    # and moves the run indexing → outlining.
    on_intake_indexed(session, version.id)
    job.status = IngestJobStatus.SUCCEEDED
    session.commit()
```

If Docling fails, the ingest worker marks the version FAILED **and** `fail_run_for_intake(session, version.id, reason)` so the run does not sit in `indexing` forever.

Outline (and later items/lesson) are **not** done inside `ingest_jobs`. The same `run_forever` loop claims `generation_jobs` when ingest is idle:

```python
# backend/src/education_platform/workers/runner.py  (excerpt)

from education_platform.modules.generation.worker import (
    claim_next_generation_job,
    process_generation_job_sync,
)

def poll_once(*, parse_pdf=None, session=None):
    db = session or _sync_session()
    ingest_id = claim_next_job(db)  # existing ingest_jobs SKIP LOCKED
    if ingest_id is not None:
        process_ingest_job_sync(str(ingest_id), parse_pdf=parse_pdf)
        return ingest_id
    gen_id = claim_next_generation_job(db)
    if gen_id is not None:
        process_generation_job_sync(gen_id)
        return gen_id
    return None
```

```python
# backend/src/education_platform/modules/generation/worker.py  (sync)

def process_generation_job_sync(job_id: UUID, *, write_outline: OutlineWriter | None = None) -> None:
    """Claimed row is already running. kind=outline in slice 1.
    Writes content_generation_outline_nodes, phase → outline_review.
    Intake version stays READY. Never publishes. Never inserts Subtopic rows.
    """
    raise NotImplementedError
```

`write_outline` is injectable, same idea as today's `write_lesson`. Tests fake it. Production uses OpenRouter when configured; otherwise a pure heading-aggregation skeleton from `section_heading` + token mass so HITL 1 is still demoable.

---

## Call site 3 — generation HTTP router (thin)

```python
# backend/src/education_platform/modules/generation/router.py

@router.post(
    "/teaching/topics/{topic_id}/generation-runs",
    status_code=202,
)
async def submit(
    topic_id: UUID,
    title: str = Form(...),
    file: UploadFile = File(...),
    target_item_count: int = Form(80),
    request: ScopedRequest = Depends(scoped("teaching.generation.submit")),
) -> AcceptedRunOut:
    accepted = await service.submit_pdf(
        request.session, request.scope, request.principal,
        topic_id=topic_id, title=title, file=file,
        target_item_count=target_item_count,
    )
    await request.record_rows(1, detail=f"submitted={accepted.run_id}")
    return AcceptedRunOut.from_domain(accepted)


@router.get("/teaching/generation-runs/{run_id}")
async def show(
    run_id: UUID,
    request: ScopedRequest = Depends(scoped("teaching.generation.get")),
) -> GenerationRunOut:
    run = await service.get_run(request.session, request.scope, run_id)
    return GenerationRunOut.from_domain(run)


@router.get("/teaching/topics/{topic_id}/generation-runs")
async def list_for_topic(
    topic_id: UUID,
    request: ScopedRequest = Depends(scoped("teaching.generation.list")),
) -> list[GenerationRunOut]:
    rows = await service.list_runs(request.session, request.scope, topic_id)
    return [GenerationRunOut.from_domain(row) for row in rows]


@router.patch("/teaching/generation-runs/{run_id}/outline")
async def patch(
    run_id: UUID,
    body: OutlinePatchIn,
    request: ScopedRequest = Depends(scoped("teaching.generation.patch")),
) -> GenerationRunOut:
    run = await service.patch_outline(
        request.session, request.scope, run_id, body.to_domain(),
    )
    return GenerationRunOut.from_domain(run)


@router.post("/teaching/generation-runs/{run_id}/accept-outline")
async def accept(
    run_id: UUID,
    request: ScopedRequest = Depends(scoped("teaching.generation.accept")),
) -> GenerationRunOut:
    run = await service.accept_outline(
        request.session, request.scope, request.principal, run_id,
    )
    return GenerationRunOut.from_domain(run)


@router.post(
    "/teaching/subtopics/{subtopic_id}/lesson-proposals",
    status_code=202,
    deprecated=True,
)
async def submit_alias(
    subtopic_id: UUID,
    title: str = Form(...),
    file: UploadFile = File(...),
    request: ScopedRequest = Depends(scoped("teaching.generation.submit")),
) -> AcceptedRunOut:
    """Resolve parent topic; same as submit on that topic. Do not treat the
    path leaf as the generated lesson's home.
    """
    accepted = await service.submit_pdf_for_subtopic_alias(
        request.session, request.scope, request.principal,
        subtopic_id=subtopic_id, title=title, file=file,
    )
    return AcceptedRunOut.from_domain(accepted)
```

Authorization is `scoped()` plus `require_role("teacher", "administrator")` on the router. Teachers must have the offering in `scope.taught_offering_ids`. Administrators are `scope.unrestricted`. The worker remains unauthenticated.

Old `GET /teaching/lesson-proposals/{id}` and `GET /teaching/subtopics/{id}/lesson-proposals` return **410 Gone**. Unreleased API; do not keep SMV-id identity.

---

## Later slices — signatures reserved, not slice-1 HTTP

There is **no** `POST .../generate`. Accept is the resume. Slice 2 changes `accept_outline` to enqueue `generation_jobs` (`items` + `lesson`). The teacher keeps polling `get_run` until `qa_review`.

```python
# slice 4 — still generation.service; still one run id

async def get_run(...) -> GenerationRun:
    """When phase is qa_review / published, include draft lesson markdown and
    the teacher QA table (prompts, options, keys, rationales). Student routes
    never call this.
    """

async def reject_items(
    session, scope, principal, run_id: UUID, *, question_ids: Sequence[UUID],
) -> GenerationRun:
    """qa_review only. Marks those DRAFT questions rejected, enqueues
    generation_jobs(kind=regenerate_items). Phase → generating until back at QA.
    """
    raise NotImplementedError  # slice 4


async def publish(
    session, scope, principal, run_id: UUID,
) -> PublishedTopic:
    """qa_review → published. Writes topic-scoped slug=lesson SMV published +
    markdown from the run. Releases the run's DRAFT topic_mastery QuizVersion.
    Worker never calls this. Idempotent if already published.
    """
    raise NotImplementedError  # slice 4


async def discard(
    session, scope, principal, run_id: UUID,
) -> None:
    """outline_review | qa_review | failed → discarded. Does not delete the
    READY intake PDF. Illegal while indexing/outlining/generating (worker owns
    the row). Not required in slice 1 because failed is terminal for the
    in-flight unique (a new submit is allowed).
    """
    raise NotImplementedError  # later
```

Student catalog (slice 4, not generation HTTP):

```python
# materials/queries.py
async def published_topic_material_version(session, topic_id: UUID) -> SourceMaterialVersion | None:
    """Parallel to published_material_version. Max published version under the
    topic-scoped slug=lesson parent. None for seeded-only topics.
    """
    raise NotImplementedError  # slice 4


# GET /topics/{topic_id}/material  — enrollment-gated, markdown only
# directory.py: if a published run exists for the topic, unlock topic_mastery
# when that lesson is published; do not wait for per-subtopic quizzes.
# Topics with no published run keep "pass all available subtopic quizzes."
```

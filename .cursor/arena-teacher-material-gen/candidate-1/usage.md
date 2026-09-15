# Teacher lesson drafts

A teacher (or unrestricted administrator) submits a PDF for a taught subtopic. The existing ingest worker indexes it, then writes lesson markdown onto the same `SourceMaterialVersion`. Students keep seeing the seeded published lesson until someone calls `approve`. Discard never publishes.

Callers import `education_platform.modules.generation.service` (HTTP) or `education_platform.modules.generation.worker` (ingest process). They never import ingest job rows, RAG wire schemas, or `SourceMaterialVersionStatus`.

## Quickstart

```python
from education_platform.modules.generation.service import (
    approve,
    discard,
    get_draft,
    list_drafts,
    retry,
    submit_pdf,
)

# 1. Enqueue. Returns immediately with a draft id to poll.
accepted = await submit_pdf(session, scope, principal, subtopic_id, title, upload)

# 2. Poll until the phase is awaiting_review or failed. PROCESSING means the
#    worker still owns the row (Docling and/or markdown synthesis).
draft = await get_draft(session, scope, accepted.draft_id)

# 3. Preview uses draft.markdown / draft.slides. This is not the student lesson GET.
# 4. Human gate — one call publishes the lesson (superseding the seeded
#    published version) and releases a 5-question mastery quiz bound to it.
published = await approve(session, scope, principal, accepted.draft_id)

# Or reject the proposal. Indexed PDF remains on disk; version becomes discarded.
await discard(session, scope, principal, accepted.draft_id)
```

`list_drafts(session, scope, subtopic_id)` is the inbox: processing, failed, and awaiting-review rows for that subtopic. The live student lesson is not in this list; it stays on `GET /subtopics/{id}/material`.

## What the caller does not do

- Does not POST `/admin/subtopics/{id}/materials`. That path stays administrator index-only and does not generate markdown.
- Does not set `lifecycle_status=published` or write `content_markdown`.
- Does not poll `ingest_jobs`. The draft phase is the only status the UI needs.
- Does not call authoring `generate` / `publish_draft` to get a student-visible quiz. Approve binds `QuizItem`s.
- Does not change `published_material_version`. After approve, that query starts returning the new row because it is the latest published version under the subtopic.

---

## Call site 1 — teacher `LessonDraftsPage`

New rail route `/teacher/lessons`. Subtopic picker copied from the question bank (taught offerings only). Upload + poll copied from admin ingest chrome, pointed at generation HTTP. Approve / Discard copied from the question bank's per-item actions.

```ts
// frontend/src/api/generation.ts  (new)
import { apiRequest } from "./client";
import type { LessonDraft, AcceptedDraft, PublishedLesson } from "./generationTypes";

export async function submitLessonPdf(
  subtopicId: string,
  file: File,
  title: string,
): Promise<AcceptedDraft> {
  const body = new FormData();
  body.append("file", file);
  body.append("title", title);
  return apiRequest<AcceptedDraft>(
    `/generation/subtopics/${encodeURIComponent(subtopicId)}/drafts`,
    { method: "POST", body },
  );
}

export async function getLessonDraft(draftId: string): Promise<LessonDraft> {
  return apiRequest<LessonDraft>(`/generation/drafts/${encodeURIComponent(draftId)}`);
}

export async function listLessonDrafts(subtopicId: string): Promise<LessonDraft[]> {
  return apiRequest<LessonDraft[]>(
    `/generation/subtopics/${encodeURIComponent(subtopicId)}/drafts`,
  );
}

export async function approveLessonDraft(draftId: string): Promise<PublishedLesson> {
  return apiRequest<PublishedLesson>(
    `/generation/drafts/${encodeURIComponent(draftId)}/approve`,
    { method: "POST" },
  );
}

export async function discardLessonDraft(draftId: string): Promise<void> {
  await apiRequest<void>(`/generation/drafts/${encodeURIComponent(draftId)}`, {
    method: "DELETE",
  });
}

export async function retryLessonDraft(draftId: string): Promise<AcceptedDraft> {
  return apiRequest<AcceptedDraft>(
    `/generation/drafts/${encodeURIComponent(draftId)}/retry`,
    { method: "POST" },
  );
}

const REVIEW_TERMINAL = new Set(["awaiting_review", "failed", "discarded", "published"]);

export async function pollLessonDraft(
  draftId: string,
  signal?: AbortSignal,
): Promise<LessonDraft> {
  for (;;) {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    const draft = await getLessonDraft(draftId);
    if (REVIEW_TERMINAL.has(draft.phase)) return draft;
    await new Promise((r) => setTimeout(r, 1500));
  }
}
```

```tsx
// frontend/src/pages/teacher/LessonDraftsPage.tsx  (excerpt)
async function onUpload(subtopicId: string, file: File) {
  const accepted = await submitLessonPdf(subtopicId, file, file.name.replace(/\.pdf$/i, ""));
  const draft = await pollLessonDraft(accepted.draft_id, abort.signal);
  if (draft.phase === "failed") {
    setError(draft.failure_reason ?? "Generation failed");
    return;
  }
  setSelected(draft); // markdown + slides for MarkdownContent preview
}

async function onApprove(draftId: string) {
  setBusyId(draftId);
  const published = await approveLessonDraft(draftId);
  setNote(
    published.quiz_released
      ? "Lesson is live. A 5-question quiz is released for this subtopic."
      : "Lesson is live. Quiz was skipped (no usable questions).",
  );
}

async function onDiscard(draftId: string) {
  setBusyId(draftId);
  await discardLessonDraft(draftId);
}
```

`SubjectMaterialsPage` stays a read-only view of **published** student lessons. A teacher who wants to see what students see still opens it after approve.

---

## Call site 2 — ingest worker (same process, new target kind)

Admin index jobs are unchanged. Teacher submit enqueues `IngestTargetKind.LESSON_DRAFT` against the new version id. After Docling/chunk/embed, the worker asks generation to finish the draft.

```python
# backend/src/education_platform/workers/ingest.py  (dispatch excerpt)

from education_platform.modules.generation.worker import finish_lesson_draft
from education_platform.modules.rag.models import IngestTargetKind

def process_ingest_job_sync(ingest_job_id: str, *, parse_pdf: ParsePdfFn | None = None) -> None:
    # ... claim validation unchanged ...
    if claim.target_kind == IngestTargetKind.SOURCE_MATERIAL_VERSION:
        _process_source_material(session, job, parse)
    elif claim.target_kind == IngestTargetKind.KNOWLEDGE_DOCUMENT_VERSION:
        _process_knowledge_document(session, job, parse)
    elif claim.target_kind == IngestTargetKind.LESSON_DRAFT:
        _process_source_material(
            session,
            job,
            parse,
            required_roles=["teacher", "administrator"],
            skip_if_chunks_exist=True,
        )
        finish_lesson_draft(session, job)
    else:
        _fail_job(session, job, f"Unknown target kind: {claim.target_kind}")
```

`finish_lesson_draft` writes `content_markdown`, validates `## Slide N` headings, sets the version to `ready`, and marks the job succeeded. It does not publish. If markdown synthesis fails, the version is `failed`, chunks stay, and `retry` can enqueue another `LESSON_DRAFT` job for the same version id (Docling is skipped because chunks already exist).

---

## Call site 3 — generation HTTP router (thin)

```python
# backend/src/education_platform/modules/generation/router.py

@router.post("/generation/subtopics/{subtopic_id}/drafts", status_code=202)
async def submit(
    subtopic_id: UUID,
    title: str = Form(...),
    file: UploadFile = File(...),
    request: ScopedRequest = Depends(scoped("generation.submit")),
) -> AcceptedDraftOut:
    accepted = await service.submit_pdf(
        request.session, request.scope, request.principal,
        subtopic_id=subtopic_id, title=title, file=file,
    )
    return AcceptedDraftOut.from_domain(accepted)

@router.get("/generation/drafts/{draft_id}")
async def show(
    draft_id: UUID,
    request: ScopedRequest = Depends(scoped("generation.draft")),
) -> LessonDraftOut:
    draft = await service.get_draft(request.session, request.scope, draft_id)
    return LessonDraftOut.from_domain(draft)

@router.post("/generation/drafts/{draft_id}/approve")
async def publish(
    draft_id: UUID,
    request: ScopedRequest = Depends(scoped("generation.approve")),
) -> PublishedLessonOut:
    published = await service.approve(
        request.session, request.scope, request.principal, draft_id
    )
    return PublishedLessonOut.from_domain(published)
```

Authorization is `scoped()` plus `require_role("teacher", "administrator")` on the router. Teachers must have the offering in `scope.taught_offering_ids`. Administrators are `scope.unrestricted` and may approve any draft in the institution. The worker remains unauthenticated.

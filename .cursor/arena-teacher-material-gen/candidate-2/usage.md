# Teacher lesson proposals

A teacher (or an in-institution administrator) submits a PDF for a taught subtopic. The existing ingest worker indexes it, then writes lesson markdown (and an optional small bound quiz) onto that same unpublished version. Students keep the seeded published lesson until a human **approves**. Discard throws the proposal away. Nothing auto-publishes.

Callers never talk to `ingest_jobs`, Docling, or `lifecycle_status` strings. They submit, poll, preview, approve, or discard a `LessonProposal`.

## Quickstart

```text
Teacher JWT
  POST   /api/v1/teaching/subtopics/{subtopic_id}/lesson-proposals   (multipart PDF)
         → 202 ProposalAccepted { proposal_id, phase: "processing" }

  GET    /api/v1/teaching/lesson-proposals/{proposal_id}
         poll until phase is awaiting_review | failed
         (processing covers queued + index + generate)

  GET    /api/v1/teaching/lesson-proposals/{proposal_id}/preview
         markdown slides + optional quiz with answer keys (teacher only)

  POST   /api/v1/teaching/lesson-proposals/{proposal_id}/approve
         → published lesson (supersedes seed) + released quiz if one was generated

  DELETE /api/v1/teaching/lesson-proposals/{proposal_id}
         → discarded; students unchanged

  GET    /api/v1/teaching/subtopics/{subtopic_id}/lesson-proposals
         open and recent proposals for that subtopic
```

Auth is `scoped("teaching.proposals")` — the same `Scope` as authoring: `taught_offering_ids` for teachers, unrestricted for administrators. Routes are `/teaching/...`, not `/admin/...` with a teacher token.

`GET /subtopics/{id}/material` and the learning directory are untouched. They still resolve `lifecycle_status=published` AND non-empty markdown. A processing or awaiting-review version on slug `"lesson"` is invisible there.

## What the worker does (not an HTTP caller)

The worker process is unchanged: `uv run python -m education_platform.workers` claims `ingest_jobs`. After Docling chunk/embed of a **proposal** version, it calls `proposals.complete_from_chunks` and leaves the version **unpublished**. Job `succeeded` means “ready for a human,” not “students can see it.”

## Call site 1 — teacher page (new route)

`/teacher/lessons` is a sibling of the question bank, not an extension of `SubjectMaterialsPage`. That page stays a read-only catalog of **published** student material.

```tsx
// frontend/src/pages/teacher/LessonProposalsPage.tsx
import {
  approveProposal,
  discardProposal,
  fetchProposal,
  fetchTaughtSubtopics,
  listProposals,
  submitProposal,
  type LessonProposal,
} from "../../api/teachingProposals";

async function onUpload(subtopicId: string, file: File) {
  const accepted = await submitProposal(subtopicId, file, "Linear equations worksheet");
  // accepted.phase === "processing"; poll by proposal_id (the material version id)
  let current = await fetchProposal(accepted.proposal_id);
  while (current.phase === "processing") {
    await sleep(1500);
    current = await fetchProposal(accepted.proposal_id);
  }
  // current.phase is "awaiting_review" or "failed"
}

async function onApprove(proposal: LessonProposal) {
  await approveProposal(proposal.id); // idempotent if already published
  // SubjectMaterialsPage / student lesson GET now resolve the new markdown
}

async function onDiscard(proposal: LessonProposal) {
  await discardProposal(proposal.id);
}
```

Chrome to copy: question-bank tabs (“waiting” / “approved”), per-row Approve/Discard + `busyId`; curriculum-upload dropzone + status badge for the processing interval. Map `awaiting_review` to “Ready to review,” never to the admin ingest badge’s “Ready” (that still means index-only).

## Call site 2 — thin HTTP router

```python
# modules/proposals/router.py
@router.post(
    "/teaching/subtopics/{subtopic_id}/lesson-proposals",
    response_model=ProposalAcceptedOut,
    status_code=202,
)
async def submit(
    subtopic_id: UUID,
    title: str = Form(...),
    file: UploadFile = File(...),
    request: ScopedRequest = Depends(scoped("teaching.proposals.submit")),
) -> ProposalAcceptedOut:
    proposal = await service.submit_pdf(
        request.session, request.scope, request.principal,
        subtopic_id=subtopic_id, title=title, file=file,
    )
    await request.record_rows(1, detail=f"submitted={proposal.id}")
    return ProposalAcceptedOut.from_proposal(proposal)

@router.post("/teaching/lesson-proposals/{proposal_id}/approve", status_code=204)
async def approve(
    proposal_id: UUID,
    request: ScopedRequest = Depends(scoped("teaching.proposals.approve")),
) -> None:
    await service.approve(request.session, request.scope, request.principal, proposal_id)
    await request.record_rows(1, detail=f"approved={proposal_id}")
```

The router maps domain `LessonProposal` → HTTP models. It does not import `IngestJob`, `SourceChunk`, or RAG schemas.

## Call site 3 — ingest worker after index

```python
# workers/ingest.py, end of _process_source_material after _persist_and_embed
from education_platform.modules.proposals.generate import complete_from_chunks

if version.submitted_by_user_id is not None:
    complete_from_chunks(session, version)
    # version.lifecycle_status == AWAITING_APPROVAL, content_markdown set, unpublished
else:
    version.lifecycle_status = SourceMaterialVersionStatus.READY  # admin index-only, unchanged
job.status = IngestJobStatus.SUCCEEDED
session.commit()
```

Admin `POST /admin/subtopics/{id}/materials` is unchanged: `submitted_by_user_id` is null, worker stops at `READY`, no markdown. Teacher submit is the only enqueue that asks the worker to generate.

# Topic generation runs (synthesized)

A teacher submits a PDF **on a topic**. That mints a `GenerationRun`. The run is the only object the UI polls. The PDF becomes a topic-scoped `SourceMaterialVersion` that Docling indexes to **READY**. Outline, later items, later lesson, and both human gates live on the run. Students see nothing until HITL 2 publish copies a topic lesson + released `topic_mastery` quiz into existing student tables.

Import `education_platform.modules.generation.service` (HTTP) or `education_platform.modules.generation.worker`. Never import `IngestJob`, `GenerationJob`, SMV statuses, or RAG wire schemas.

`LessonProposal` / `complete_from_chunks` go away. `POST /teaching/subtopics/{id}/lesson-proposals` is a **deprecated alias** onto the parent topic.

Types and storage: [shape.md](../candidate-1/shape.md) plus grafts below. Rationale: [rationale.md](rationale.md).

## Quickstart (slice 1 — outline HITL)

```python
from education_platform.modules.generation.service import (
    accept_outline,
    discard_outline,
    get_run,
    list_runs,
    patch_outline,
    retry_failed,
    submit_pdf,
)

accepted = await submit_pdf(
    session, scope, principal,
    topic_id=topic_id, title=title, file=upload,
    target_item_count=80,  # optional; clamped 60–80, default 80
)
# 202. Poll run_id — not an SMV id.

run = await get_run(session, scope, accepted.run_id)
# indexing       ingest_jobs owns the PDF
# outlining      generation_jobs kind=outline
# outline_review HITL 1; PATCH + accept or discard
# failed         ingest failed the PDF, or outline failed (PDF may already be READY)
# discarded      teacher abandoned; new submit allowed

run = await patch_outline(session, scope, accepted.run_id, outline_patch)
# Replace the outline document. No Subtopic writes. Quotas previewed, not frozen.

run = await accept_outline(session, scope, principal, accepted.run_id)
# Freeze quotas (Largest Remainder), match-or-create Subtopic + LearningOutcome.
# Phase → generating. Slice 1 does not enqueue item/lesson jobs.

run = await discard_outline(session, scope, principal, accepted.run_id)
# outline_review | failed → discarded. Live curriculum untouched. Intake stays READY.

run = await retry_failed(session, scope, principal, accepted.run_id)
# failed + intake READY (outline died): re-enqueue kind=outline, phase outlining.
# failed + intake FAILED (index died): 409 — re-upload via submit_pdf.
```

`list_runs(session, scope, topic_id)` is the inbox (in-flight first, then newest).

Admin `POST /admin/subtopics/{id}/materials` is unchanged: index-only, READY, no run.

## Failure rules (graft)

| What failed | Intake SMV | Run | Recovery |
| --- | --- | --- | --- |
| Index / Docling | `FAILED` | `failed` | New `submit_pdf` (lock clear because failed is terminal) or later re-index if we add it |
| Outline LLM / empty headings | stays `READY` | `failed` | `retry_failed` on the same run |
| Later items / lesson | stays `READY` | `failed` | retry those jobs (slice 2+) |

Worker never writes `published` / `released`.

## HTTP (thin)

- `POST /teaching/topics/{topic_id}/generation-runs` → 202 `{ run_id, topic_id, phase: indexing }`
- `GET /teaching/generation-runs/{run_id}`
- `GET /teaching/topics/{topic_id}/generation-runs`
- `PATCH /teaching/generation-runs/{run_id}/outline`
- `POST /teaching/generation-runs/{run_id}/accept-outline`
- `POST /teaching/generation-runs/{run_id}/discard`
- `POST /teaching/generation-runs/{run_id}/retry`
- Deprecated alias: `POST /teaching/subtopics/{subtopic_id}/lesson-proposals` → same AcceptedRun
- Old proposal GET/LIST → **410 Gone**

Auth: `require_role("teacher", "administrator")` + `taught_offering_ids` (admin unrestricted). Worker unauthenticated.

## Worker

Same process as ingest. After source version READY, `on_intake_indexed` is a no-op for admin; for a run in `indexing` it sets `outlining` and inserts `generation_jobs(kind=outline)` in the **same commit**. `run_forever` claims ingest first, then generation jobs. No new `IngestTargetKind`.

## Later slices (signatures only)

`reject_items`, `publish` stay on `generation.service`. Publish writes topic `slug=lesson` published markdown from the run and releases `topic_mastery`. `GET /topics/{id}/material` in slice 4. Directory: if a published topic lesson exists, unlock topic quiz from that lesson; else keep pass-all-subtopic-quizzes. Seeded leaf lessons stay.

There is **no** `POST .../generate`. Accept is the resume.

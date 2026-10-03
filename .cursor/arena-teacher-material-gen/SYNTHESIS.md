# Synthesized design: teacher lesson proposals

Base: candidate-2. Cross-judge: [39eccab3](39eccab3-870a-446e-b7af-e5fde0c45dc8). Parent agreed.

## Synthesis decision

Candidate-2 is the base. `awaiting_approval` is a real stored phase. Admin `READY` stays index-only. Teachers submit, poll, preview, approve, or discard a `LessonProposal`. The existing ingest worker indexes, then generates, and never publishes.

Grafted from candidate-1:

- `retry` from `FAILED` (re-enqueue same version, skip Docling when chunks exist).
- Constructor invariants: awaiting_review/published require validated slides; failed requires a reason.

Folded while grafting (C2 red flag, not a C1 average):

- In-flight partial unique applies only where `submitted_by_user_id IS NOT NULL` and `lifecycle_status IN ('processing', 'awaiting_approval')`. Admin index-only uploads are not blocked by a teacher proposal.

Rejected from candidate-1: READY+markdown as wait state; quiz on approve; `IngestTargetKind.LESSON_DRAFT`; heuristic markdown as a successful reviewable lesson; flipping student retrieval roles onto proposal PDF chunks at approve.

## Data shape

One `LessonProposal` is one `SourceMaterialVersion` on slug `"lesson"` with `submitted_by_user_id` set.

`ProposalPhase`: processing → awaiting_review | failed → published | discarded.

Storage: `processing` / `awaiting_approval` / `failed` / `published` / `archived`.

Students see only `published` + markdown. Seed stays until approve supersedes.

Quiz is a passenger: draft rows in the worker, teacher preview with keys, release on approve. Lesson can await review with `quiz=None`.

## Public operations

`submit_pdf`, `get_proposal`, `list_proposals`, `approve`, `discard`, `retry`.

HTTP under `/teaching/lesson-proposals*`. `scoped()` plus teacher/administrator. Worker unauthenticated.

## First implementable unit (this slice)

Schema + enqueue + get/list while `processing`. No LLM, no approve, no frontend.

Success: a taught teacher JWT POSTs a PDF, gets 202 with `phase=processing`, GET returns that proposal, students still see the seeded lesson, admin ingest still ends at READY with null `submitted_by`.

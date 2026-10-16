# Rationale

## Problem

Teachers need to turn a taught-subtopic PDF into a student lesson without that lesson becoming visible until a human says so. Indexing already exists (`ingest_jobs` + Docling worker → `SourceMaterialVersion.lifecycle_status=ready`, empty markdown). Student visibility is a different switch: `published` plus non-empty `content_markdown`, resolved by `published_material_version` across every material under the subtopic. Seed and admin ingest already share slug `"lesson"`, so a second published identity races unless the resolver changes. Ingest HTTP is `require_administrator`; teacher reach is `Scope.taught_offering_ids`. Authoring's `DRAFT → publish_draft` is the live approve/discard UX but it does not attach `QuizItem`s and must not become the student quiz path. The worker is unauthenticated. Product forbids LangGraph, a second service, Redis, MinIO, and auto-publish. Design 04 already named Ready → Published as the human gate; that HTTP step was never built.

## Usage (caller's view)

A teacher (or unrestricted admin) calls `submit_pdf` and polls `get_draft` until `awaiting_review` or `failed`. Preview reads `draft.markdown`. `approve` publishes the lesson onto the existing `"lesson"` parent (superseding seed) and releases a 5-question mastery quiz; `discard` archives. The worker, after the same Docling path, calls `finish_lesson_draft` and stops at `ready`. Call sites: `LessonDraftsPage` (`/teacher/lessons`), ingest dispatch on `IngestTargetKind.LESSON_DRAFT`, thin `generation/router.py`. Teachers do not POST `/admin/...`. `SubjectMaterialsPage` stays the published student view. Full README and snippets: `usage.md`.

## Shape

Data structures first: `DraftPhase` is the lifecycle. It is projected from the existing version enum — `processing` / `ready`+markdown / `published` / `failed` / `archived` — so we do not add statuses or a parallel boolean (`ready` and `content_markdown is not None`). `LessonMarkdown` is the only type that may hold student-study text; its constructor requires `parse_slides` to return at least one slide. `LessonDraft` forbids awaiting-review or published without that markdown.

Identity: keep slug `"lesson"` and leave `published_material_version` alone. A READY PDF version already sits beside a published seed version on that parent; students keep the seed until approve supersedes it. That is the constraint the unique index `uq_source_material_versions_one_published` already enforces.

Where generation runs: same worker, new `IngestTargetKind.LESSON_DRAFT`, after chunk/embed, before `ready`. Admin `SOURCE_MATERIAL_VERSION` stays index-only so `CurriculumMaterialUpload` does not grow an OpenRouter dependency. No API-side job: HTTP would either block on Docling or invent a second poll surface. `PROCESSING` covers both index and synthesis so the frontend keeps one terminal set.

HTTP: `/generation/...` with `scoped()` and `require_role("teacher","administrator")`, not teacher JWT on `/admin`. Admin ingest remains a 403 for teachers. Approver is whoever can teach the offering; admins are unrestricted. Worker stays unauthenticated; auth is on enqueue and on approve.

Quiz: generated inside `approve` from the approved markdown, persisted through existing assessment tables, released and bound with `QuizMaterialBinding`. Five questions, `authoring.validate` reused, no Bloom/LangGraph stack. If the model yields nothing, the lesson still publishes (`quiz_released=False`). Quiz is not generated in the worker so a failed quiz LLM cannot fail an already-good index, and the question-bank drafts tab does not become a second inbox of unbound items.

Retrieval: LESSON_DRAFT embeddings start as teacher+admin; approve adds student. That closes the READY-chunk leak into `retrieve_chunks` for this path.

Interface depth: five operations (`submit_pdf`, `get_draft`/`list_drafts`, `approve`, `discard`, `retry`) hide blob storage, job enqueue, Docling, markdown synthesis, supersede, embedding ACL, and quiz release. Callers never see `IngestJob`, RAG wire types, or version-status strings. Complexity that stays exposed: the poll loop (the worker is a separate process; hiding it would mean a blocking upload). Per boundary-discipline, parse UploadFile at `accept_source_pdf`; per encode-lessons-in-structure, illegal phases are unrepresentable on `LessonDraft`. Per make-operations-idempotent, re-approve of the same published version and re-discard are no-ops. Per separate-before-serializing-shared-state, concurrent publishes serialize on the partial unique index rather than a lock service.

## Synthesis decision

Filled by arena orchestrator.

## Tradeoffs accepted

- We accept one version row holding both a PDF blob and generated markdown in exchange for a single id from upload to approve and no resolver change.
- We accept `content_format="pdf"` on a row that students will read as markdown in exchange for not lying about the blob; student GET already keys off markdown, not format.
- We accept a new ingest target kind (Alembic enum + check constraint) in exchange for keeping admin index-only behavior unchanged.
- We accept collapsing index and synthesis into one `PROCESSING` interval in exchange for not teaching the UI a `GENERATING` state. A long Docling+LLM run looks like one spinner.
- We accept quiz generation on the approve HTTP request (seconds, like authoring generate) in exchange for a fast worker finish and a single human gate.
- We accept approved quiz questions also appearing in the question-bank "approved" list in exchange for not adding a question status or a sidecar table.
- We accept heuristic markdown when `OPENROUTER_API_KEY` is missing (chunk headings packed into slides) in exchange for a demoable worker without a second stub service. The human still must approve.
- We accept not recording `requested_by` on `ingest_jobs` in exchange for no schema on the unauthenticated worker table; audit on submit/approve is the identity trail.
- We accept that dual-role users remain unrestricted admins (`scope_for` unchanged) in exchange for not reopening authorization.
- We accept always-latest published resolution after approve (in-progress students re-bind, quizzes re-lock) in exchange for not implementing design 04's bound-old-version behavior, which the current student GET does not do.

## Alternatives considered

**Two identities: `slug="source-pdf"` (never published) plus a new markdown version on `"lesson"`.** Rejected. Callers would juggle two ids (poll the PDF, approve the lesson). `published_material_version` ignores slug and would still pick a published PDF if anyone ever published it, so the safety of the split is a convention, not a type. Interface is larger (source vs lesson) while hiding less: the caller learns the pipeline's internals. The chosen shape hides the PDF behind one `draft_id`.

**Generate in the API after READY, no new target kind.** Rejected. Either `submit_pdf` blocks on Docling+LLM (HTTP timeout, no reuse of the worker) or the UI polls READY then fires a second "generate" call (caller coordinates two stages — shallow). Product said reuse the worker.

**Extra version statuses (`generating`, `awaiting_approval`).** Rejected. They leak pipeline stages onto the public surface and force every poll client (admin included) to learn new terminals. `DraftPhase` already names the caller-facing machine; storage stays the enum design 04 specified (`ready` = waiting for a human).

**Put upload+approve on `/admin/subtopics/...` and allow teacher JWT.** Rejected. Teachers 403 today for a reason; widening admin routes mixes catalog ingest with assignment-scoped authoring. Authoring already has the correct scope pattern. Interface would expose administrator-only neighbors (knowledge docs, policy chats) as if they were in the same capability.

**Extend `SubjectMaterialsPage` with upload.** Rejected. That page is the student-visible published tree. Mixing "what the class sees" with "what I have not approved" is information leakage in the UX. A dedicated `/teacher/lessons` inbox matches the question bank's generate-then-approve loop without contaminating published preview.

**Authoring-only quiz: teacher generates questions, then a separate bind step.** Rejected. Callers would coordinate generate → publish_draft × N → some new attach endpoint. Shallow. Approve as one operation hides bind/release.

**New `lesson_drafts` table as the state machine, versions remaining ingest-only.** Rejected. Two sources of truth for "is this student-visible?" (draft row vs `lifecycle_status`). Publish would have to sync them. The version row already is the lifecycle.

## Open questions and risks

- Should Demo School seed a teacher (`teacher@demo.school` + Grade 8 MATH assignment) so this path is demoable without the Al Noor synthetic CLI?
- When heuristic slides are what the teacher reviews, is that acceptable for classrooms without an API key, or should `finish_lesson_draft` fail closed until OpenRouter is configured?
- Approve currently generates quiz items the teacher did not preview. Is post-approve question-bank editing enough, or must v1 show the five questions on the draft (which pushes quiz generation back into the worker)?
- `set_required_roles` on `chunk_embeddings` has no FK and uses a separate engine today. Can approve's ACL flip live in the same transaction as publish, or do we accept a short window where published markdown exists but retrieval roles still exclude students?
- Stuck `running` ingest jobs still cannot be reclaimed. Should retry be offered for `PROCESSING` older than N minutes, or is that out of v1?
- Parent `SourceMaterial.status` is unused on student reads. Do we still set it `published` on approve for catalog consistency, knowing it does not gate anyone?

## Next implementation step

Add `IngestTargetKind.LESSON_DRAFT` (Alembic + claim contract), extract `rag.intake.accept_source_pdf`, and make the worker dispatch into a `finish_lesson_draft` that writes validated markdown and stops at `ready`.

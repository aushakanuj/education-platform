# Rationale

## Problem

Teachers need to turn a subtopic PDF into student-visible lesson markdown without students seeing it until a human approves. Indexing already exists (`ingest_jobs` + Docling + MiniLM, stopping at `READY` with empty markdown). Student visibility is a different switch: `SourceMaterialVersion.lifecycle_status=published` and non-empty `content_markdown`, resolved by max version number under the subtopic — and seed plus PDF ingest already share slug `"lesson"`, so a careless publish supersedes the common lesson for every enrolled student. Ingest HTTP is administrator-only; the worker is unauthenticated; authoring’s generate/approve path is questions, not materials, and does not attach `QuizItem`s. The non-obvious part is owning generation and the human gate without a second queue, without overloading admin `READY`, and without a second published identity that the resolver would race.

## Usage (caller's view)

Teachers and unrestricted admins call five operations on `/teaching/lesson-proposals`: submit PDF, poll, preview (slides + keys), approve, discard. The frontend is a new `/teacher/lessons` page, not the published catalog. The worker, after indexing a version that has `submitted_by_user_id`, calls `complete_from_chunks` and still does not publish. Types in `shape.md` match this: callers hold a `LessonProposal` whose `id` is the version id and whose `phase` is the only status they need. See `usage.md` for the README and the three call sites (page, router, worker).

## Shape

The public surface is one deep module, `modules/proposals`. It hides enqueue, Docling, embeddings, LLM, slide-schema validation, supersede, and optional quiz release. Callers do not coordinate index-then-generate-then-publish.

Data: keep slug `"lesson"`. A proposal is a sibling version on that parent, unpublished until approve. That is the existing “READY can sit beside published seed” fact, extended with a real phase `awaiting_approval` instead of inferring intent from `READY` + markdown. `submitted_by_user_id` is the single source of truth for “this version must generate, and this user uploaded it.” Admin index leaves it null and still ends at `READY`.

Generation runs in the **same job, after embed**, in the existing worker. No new `IngestTargetKind`: that enum is “which table is `target_id`,” not “which pipeline.” A second kind pointing at the same version table would leak a workflow distinction into the queue schema. HTTP stays off the worker; auth lives on submit and approve.

Quiz: reuse `Question*` / `Quiz*` / `QuizItem` / `QuizRelease` / `QuizMaterialBinding`. Generate a small draft quiz in the worker; **release on approve** so students never see it early. If quiz generation fails, the lesson proposal still waits for review. Authoring lists skip question versions that already have `QuizItem`s so proposal drafts cannot be self-published through the question bank.

Interface depth: five operations vs a pipeline of upload, poll job, poll version, copy markdown, publish material, publish quiz. Complexity that remains on the caller is “wait until `awaiting_review` or `failed`,” which is inherent (the worker is another process). Validation of PDF bytes and teaching scope sits at `submit_pdf`; slide shape sits at `complete_from_chunks`; publish rules sit at `approve`. Inside, types are trusted.

In-flight uniqueness is a partial unique index, not a check-then-insert. Approve and discard are idempotent for their terminal states.

## Synthesis decision

Candidate-2 is the base (parent and cross-judge agreed). Graft from candidate-1: `retry` from FAILED, and constructor invariants on `LessonProposal` / markdown. Reject C1 READY+markdown, quiz-on-approve, and `LESSON_DRAFT` target kind. In-flight unique is proposal-only (`submitted_by_user_id IS NOT NULL`) so admin index is not blocked. Full record: `../SYNTHESIS.md`.

## Tradeoffs accepted

- We accept a new `awaiting_approval` enum value (Alembic + admin badge vocabulary) in exchange for not overloading `READY`, which already means “indexed” in the admin UI and tests.
- We accept one in-flight `processing|awaiting_approval` version per lesson material, including admin index, in exchange for no lost-update races between two teachers or teacher vs admin on the same subtopic.
- We accept generating in the sync worker (`chat_completion_json_sync`) in exchange for not holding an HTTP request across Docling+LLM and not adding a second job kind.
- We accept best-effort quiz (lesson can ship without it) in exchange for not failing a good lesson because MCQ JSON was messy.
- We accept that approve supersedes the seeded common lesson for **new** study, and that in-progress students still follow latest published (current resolver), in exchange for not inventing bound-old-version progress in this change.
- We accept dual-role admins seeing all in-institution proposals (scope short-circuits to unrestricted) in exchange for not inventing a second grant model.
- We accept proposal PDF chunks never gaining the student retrieval role in exchange for closing the “READY curriculum leaks into retrieve_chunks” hole on this path only.

## Alternatives considered

- **Parallel `lesson_drafts` table (markdown + quiz JSON + status), copy into `SourceMaterialVersion` on approve.** Rejected. It duplicates versioning the materials table already has (`draft/processing/ready/published`), splits the source of truth, and forces every reader to know which table is live. Callers would get a smaller-looking `Draft` type but a second lifecycle to keep in sync — shallower module, more surface. Interface depth loses: approve becomes a copy job instead of a status transition.
- **Same `"lesson"` version, no new status: `READY` + non-empty markdown means awaiting approval.** Rejected. Admin ingest already terminates at `READY` with empty markdown; the frontend treats `ready` as success. Callers would have to learn “ready sometimes means indexed and sometimes means please publish,” which leaks the pipeline into every poll site. A phase enum hides that.
- **New slug `teacher-lesson` plus a resolver change.** Rejected. `published_material_version` already picks max published version across **all** materials under the subtopic. A second published slug races unless we rewrite student GET and `has_lesson`. That exposes resolver policy to the generation feature. Reusing `"lesson"` plus supersede-on-approve keeps the student gate unchanged.
- **Follow-on `IngestTargetKind` or API-side generate after `READY`.** Rejected. A new kind on the same version UUID is a lying queue type. Generating in the API couples the teacher’s HTTP request to the LLM and still needs a poll story for Docling. The worker already owns long PDF work; generation is the second stage of that work, gated by `submitted_by_user_id`.
- **Extend `SubjectMaterialsPage` / copy `/admin` ingest onto a teacher JWT.** Rejected. The materials page is the published student catalog; mixing drafts there makes “what students see” and “what I proposed” one screen. Opening `/admin/subtopics/.../materials` to teachers would bypass `taught_offering_ids` unless every admin route grew assignment checks — leaking teaching policy into the admin module.

## Open questions and risks

- Should a failed proposal be retryable in place (re-queue generate on the same version) or is “upload again” enough, matching today’s failed ingest?
- If two published quiz versions exist (seed released + newly released), is “latest `version_number`” the intended student quiz, including when the teacher approved a lesson with `quiz=None`?
- Do we add a Demo School teacher seed so `/teacher/lessons` is usable without the Al Noor synthetic CLI, or keep tests on assignment fixtures only?
- Should admin index-only uploads later join this approval machine (design 04’s missing Ready→Published), or stay `READY` forever?
- When OpenRouter is unset, is failing the proposal the right teacher-visible error, or should tests-only heuristic markdown exist like the policy assistant stub?

## Next implementation step

Alembic: add `awaiting_approval` to `source_material_version_status`, `submitted_by_user_id`, the in-flight partial unique, and the awaiting-markdown check; then implement `queue_source_material_pdf` and `submit_pdf` so a teacher JWT can enqueue without generating yet.

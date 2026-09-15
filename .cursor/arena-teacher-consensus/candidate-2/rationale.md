# Rationale

## Problem

Topic generation already has a `GenerationRun` phase machine, a shared outline DAG that teachers PATCH in place, and an admin closer for accept / QA / publish. Product now needs attributed teacher review (approve vs request-changes), a hard cap of two teacher rounds, timeout-as-abstain, optional AI collation, and a teacher chat that is not the policy handbook graph — without ever giving students per-teacher lessons or letting the worker publish. Live PATCH cannot carry attribution or round policy; two teachers writing the same node list is shared mutable state. Accept today also writes live `Subtopic` rows before generate, so a consensus design must keep drafts off the curriculum tree until the closer. Callers that must keep working: admin PDF upload, student `GET /topics/{id}/material`, directory `has_topic_lesson`, subtopic admin ingest, `/admin/policy`.

## Usage (caller's view)

The UI still polls `get_run`. Teachers `put_overlay` then `submit_review` (approve / request-changes / abstain). The shared DAG does not move. Admins optionally `collate_overlays`, then `apply_merge` (the only shared write), then existing `accept_outline` / `publish`. After publish, overlays 409; `ask_revision` is a note, `submit_pdf` is the next run. Chat is `post_review_chat` on the run (generation-review graph, `core.llm`), not `/chats`. Teacher PATCH outline is 410. Full README and three call sites: [usage.md](usage.md).

## Shape

**The aggregate is the current read-only base plus per-teacher overlays.** The outline job (and later lesson/item jobs) freeze a base and a `BaseFingerprint`. Each roster teacher owns one overlay row per round. Diff is a pure function of overlay versus base, attributed by `teacher_user_id`. Merge happens at the admin read/apply boundary (`ProposedMerge` → `apply_merge`), per separate-before-serializing-shared-state. Historical overlays stay as per-actor documents keyed by `(stage, round index, teacher)`; there is no snapshot chain to diff.

`ReviewRound` encodes deadlock policy in types: `TeacherRoundIndex` is 1|2, `successor()` is `None` on 2, timeout derives `ABSTAIN`, admin `seal_round` / accept / publish always close. `ReviewStage` (outline | QA) reuses that machine; QA overlays attach to `LessonSectionRef` (one per outline node, written by the lesson job) and question ids — same put/submit, different body union. Curriculum match-or-create stays on `accept_outline`. `PublishLock.LOCKED` makes post-publish explicit.

Assistant graphs are a strategy (`POLICY` vs `GENERATION_REVIEW`) sharing `core.llm`. Generation review retrieves this run's intake chunks only. Policy `/chats` and handbook `retrieve_chunks` stay admin-only.

Interface depth: six new teaching/closer operations hide roster snapshotting, draft privacy, fingerprint concurrency, round cap, collate, UUID minting for `NodeAddOp.local_key`, and graph dispatch. Callers still see one poll object plus overlay/merge documents they already edit. Per boundary-discipline, ORM, jobs, and LangGraph state stay behind `generation.service`. Internals are `overlay.py` / `review.py` / `collate.py`, not pass-through facades and not round-numbered modules.

## Synthesis decision

Orchestrator fills after arena.

## Tradeoffs accepted

- We accept N overlay rows per round instead of one shared working copy in exchange for never serializing two teachers onto the same DAG write.
- We accept derived diffs (recomputed on GET) in exchange for a single write model; we will not persist a parallel op-log that can drift from the overlay body.
- We accept 410 on teacher `PATCH /outline` (breaking the current HITL 1 UI) in exchange for not leaving a second mutation path that bypasses rounds.
- We accept lazy timeout on GET/closer (plus optional worker sweep) in exchange for not adding a dedicated scheduler; effective stance is derived, not stored twice.
- We accept unsubmitted draft bodies becoming visible to the closer only after seal/timeout in exchange for not losing work, while still counting those teachers as abstain rather than request-changes.
- We accept dual-role admins as closer-only (no teacher overlay) in exchange for not mixing merge rights with a personal diff.
- We accept a new lesson-section table keyed by outline node in exchange for QA anchors that are not a regex over `draft_lesson_markdown`.
- We accept generation review chat in generation-owned tables, not `chat_conversations`, in exchange for keeping policy inbox uncontaminated.
- We accept locked published artifacts plus `RevisionAsk` in exchange for an explicit new-run path; teachers cannot shadow-edit the student lesson.

## Alternatives considered

**GitHub-PR snapshot chain (`OutlineRevision` N, change requests hang off a revision, collate writes N+1, diff = snapshot vs snapshot).** Rejected as this candidate's whole shape. It exposes revision arithmetic and a shared comment thread to every caller, and it still serializes teachers onto one working tree between snapshots. Overlay hides collation behind merge and keeps writes per-actor until that boundary. (Viable as the other arena candidate, not as a graft onto this one.)

**Keep live PATCH and scrape `audit` for “who asked.”** Rejected. Attribution and diffs would leak into a log format callers must reassemble; round cap and abstain cannot be encoded on PATCH. Shallow: every client reimplements review.

**CRDT / OT on outline nodes.** Rejected. A handful of teachers and two rounds do not need concurrent editing semantics; they need a closer. The public surface would grow sync protocol that the UI does not want.

**ChangeRequest rows on shared nodes while PATCH still mutates the DAG.** Rejected as a hybrid. Shared mutation remains; overlays would be comments on a moving base, so fingerprints lie.

**Copy the policy LangGraph (inject → validate → handbook retrieve → summarize) under `/teacher/assistant`.** Rejected by retrieval mix, admin-only chat ownership, and answer-key leakage. Strategy plugin is the smaller public surface: one `graph_for(kind)` hiding two graphs.

**Per-teacher student lessons or section-scoped generation.** Rejected by the one-curriculum invariant. Overlays die at publish; students keep one SMV and one `topic_mastery`.

## Open questions and risks

- What default `due_at` should a round get (72h? period-relative?), and may admin set it per run?
- After round-2 `apply_merge`, teachers are locked out of a third look; should GET still show the merged base before accept, or is closer-only correct?
- If the offering has one assigned teacher, does the roster-of-one still require two rounds, or may the closer skip collate by policy we have already allowed?
- Should `RevisionAsk` block a second in-flight run, or is the existing one-in-flight unique enough?
- Dual-role users: confirm closer-only, or should an admin who also teaches be allowed an overlay that they then merge?
- Collate with conflicting ADD local_keys from two teachers: does the LLM merge document drop both, or must `apply_merge` 400 until the admin picks?

## Next implementation step

Alembic for review rounds, teacher overlays, proposed merges, and lesson-section rows; open outline round 1 from the outline job; replace teacher `patch_outline` with `put_overlay` / `submit_review` and 410 the old PATCH.

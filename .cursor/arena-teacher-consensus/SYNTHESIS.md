# Synthesis: teacher–admin consensus

## Base

**Candidate 1 (frozen revisions / PR-style)** is the base.

It matches the school story: teachers review a frozen outline, file attributed requests, AI produces the next outline, they look again (at most twice), admin closes, then generate, then the same machine on lesson/quiz, then publish. Diffs are snapshot-versus-snapshot against the exact tree a teacher saw. The public surface is small: load workspace, submit one decision, admin close (rewrite | accept | override | discard), plus assistant turn.

Candidate 2 (per-teacher overlays) is a strong alternative for write isolation, but it exposes collate + merge as extra closer steps and makes “the new outline” an admin merge document rather than a second frozen revision teachers re-approve. That is a worse fit for “AI drafts a new outline and it goes back to teachers.”

## Grafts from candidate 2

- **410** on `PATCH .../outline` and the deprecated teacher PDF POST (no second mutation path).
- **Base fingerprint / revision id** on every write so a stale tab cannot comment on a newer tree (C1 already names revision in the command; keep that hard).
- **Lesson-section rows** keyed by outline node for QA anchors (do not regex `draft_lesson_markdown`).
- **Post-publish `RevisionAsk`** as a note only; overlays/decisions stay locked; next curriculum is admin `submit_pdf`.
- **Generation chat tables owned by the run**, not `chat_conversations` (policy inbox stays handbook-only).
- **Derived abstain** at deadline; do not store stance twice.
- **Discard legal from `qa_review`** (unpublished drafts go away; live student lesson unchanged).
- **Dual-role admin is closer-only** on this run (no personal overlay/decision unless they also have teacher role *and* we later opt in).

## Rejected

- Live PATCH + audit log as “history.”
- Unanimous auto-advance (deadlock + weak closer).
- Copying the policy LangGraph into `/teacher/assistant`.
- Per-teacher student lessons.
- CRDT/OT concurrent editing.
- Overlay-as-aggregate (C2 whole shape) — isolation is good; the product wants a shared next revision teachers re-read.

## Rubric

| Criterion | C1 | C2 |
|---|---|---|
| One curriculum / no worker publish / keys off students | pass | pass |
| No deadlock (cap, abstain, admin override) | pass | pass |
| Attribution + diff as data | **stronger** (snapshot history) | overlay-vs-base only |
| Assistant as strategy, not second LLM stack | pass | pass |
| Small public HTTP on existing GenerationRun | **deeper** (close hides rewrite) | collate+merge+seal exposed |
| Post-publish explicit | locked + new run | locked + RevisionAsk (grafted) |

## Verification

Grounding constraints are honored: admin upload, offering-scoped teachers, one in-flight run, worker never publishes, student material GET unchanged, policy `/chats` unchanged. First implementation step: revision/round/decision tables and 410 PATCH — not a chatbot, not a live-edit patch.

## Checkpoint

Do not implement until the human signs off on: review duration, whether admin can close before deadline, and whether published-is-locked is the long-term policy.

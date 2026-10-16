# Frame: teacher–admin consensus + diffs + staff chat

## Artifact

Each candidate writes three files in its output dir:

- `usage.md` — caller’s README + 2–3 realistic call sites (HTTP + UI).
- `shape.md` — types, signatures, module map, `not implemented` bodies.
- `rationale.md` — per architect rationale-template.md (leave Synthesis decision as “orchestrator fills”).

## Product (must satisfy)

School: one PDF, one outline, one lesson, one topic quiz for all students.

1. Admin uploads → outline revision frozen → assigned teachers Approve or Request changes (not live PATCH).
2. Attributed diffs: who asked, what they asked, visible like a review UI (not necessarily GitHub chrome).
3. Collate teacher requests; one bounded AI pass drafts the next outline revision (max 2 teacher rounds, then admin). Silence = abstain. Admin is always closer (accept generate / discard / override).
4. After generate: teachers comment on lesson sections and quiz items. Same round machine. Admin publish is the only student-visible write. After publish: define whether teachers can file a *new* run (revision) or the published artifact is final until admin opens a new run.
5. Teacher AI chat beside the review: help draft a change-request or explain a node. Reuse `core.llm` + a **strategy** for assistant graphs (policy vs generation). Do not copy the policy LangGraph as-is (wrong retrieval mix, admin-only chats, keys).

## Distinct shapes (assigned per candidate)

- **Candidate 1:** GitHub-PR style. Frozen `OutlineRevision` snapshots. Change requests hang off a revision. Collate produces revision N+1. Diff = snapshot vs snapshot.
- **Candidate 2:** Per-teacher overlay. Each teacher writes a private overlay; shared outline is read-only until merge. Diff = overlay vs base. Merge at admin closer. No shared mutation.

Do not converge on live PATCH.

## Rubric (picker only; candidates do not see scores)

1. One curriculum invariant (no private student lessons; worker never publishes; keys off student APIs).
2. No deadlock (timeout/abstain/round cap/admin override encoded in types).
3. Attribution + diff are first-class data, not audit-log archaeology.
4. Assistant is a strategy/plugin of graphs+tools, not a second LLM stack; policy chat stays admin handbook.
5. Fits existing `GenerationRun` / offering-scoped teaching assignments; small public HTTP surface.
6. Post-publish change is explicit (new run vs locked) rather than implied.

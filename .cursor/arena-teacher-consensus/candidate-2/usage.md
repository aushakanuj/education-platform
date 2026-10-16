# Teacher consensus via per-teacher overlays

Assigned teachers never PATCH the shared outline. The outline job (and later the lesson/items jobs) write a **read-only base**. Each teacher of the offering writes a **private overlay**. Diffs are overlay-versus-base, attributed to that teacher. The only shared write is an administrator **apply merge** (optionally after an AI collate of overlays). Admin is always the closer. Students still see one published lesson and one topic quiz.

Import `education_platform.modules.generation.service`. Do not import review-round ORM, overlay JSON, collate jobs, or LangGraph state. Policy handbook chat stays on `/chats` and `assistant.graph`; teacher review chat uses a different graph strategy and `core.llm`.

Types: [shape.md](shape.md). Rationale: [rationale.md](rationale.md).

## Quickstart

```python
from education_platform.modules.generation.service import (
    accept_outline,
    apply_merge,
    ask_revision,
    collate_overlays,
    discard_outline,
    get_run,
    list_runs,
    post_review_chat,
    publish,
    put_overlay,
    seal_round,
    submit_pdf,
    submit_review,
)

# Admin upload — unchanged. Teachers cannot submit PDFs.
accepted = await submit_pdf(session, scope, principal, topic_id=topic_id, title=title, file=upload)
run = await get_run(session, scope, accepted.run_id)
# indexing → outlining → outline_review (round 1 opens; base frozen)

# Teacher: edit a private overlay, then take a stance. Shared DAG is unchanged.
run = await put_overlay(session, scope, principal, run.id, overlay_draft)
run = await submit_review(session, scope, principal, run.id, stance=REQUEST_CHANGES)
# or stance=APPROVE (empty overlay) / ABSTAIN (explicit skip)

# Admin closer — not a teacher PATCH.
run = await collate_overlays(session, scope, principal, run.id)   # optional AI pass
run = await apply_merge(session, scope, principal, run.id, merge)  # only shared-DAG write
run = await accept_outline(session, scope, principal, run.id)      # freeze curriculum, enqueue gen
run = await publish(session, scope, principal, run.id)             # only student-visible write
```

`get_run` is still the object the UI polls. It now carries the read-only base, the caller's overlay, attributed diffs for **sealed** overlays, round clock, and any proposed merge. There is no live `patch_outline` for teachers. `PATCH /teaching/generation-runs/{id}/outline` returns **410**.

## Rules callers can rely on

| Rule | What it means |
| --- | --- |
| One curriculum | Overlays never become student lessons. Worker never publishes. Keys stay off student APIs. |
| Private until sealed | A draft overlay is visible only to its teacher. Submit (or timeout) seals it. |
| Diff = overlay vs base | Attribution is the overlay's `teacher_user_id`, not an audit-log scrape. |
| Max 2 teacher rounds per stage | Outline review and QA review each get rounds 1–2. No round 3. |
| Timeout = abstain | `due_at` passed and no submit → effective stance `ABSTAIN`. Admin can `seal_round` early. |
| Admin is closer | Accept / merge / discard / publish are legal with pending teachers (remaining → abstain). |
| System mints node ids | Overlay new-nodes use `local_key`. `apply_merge` (or the outline job) mints UUIDs. |
| Post-publish is locked | Teacher overlays 409. `ask_revision` is a note; only admin `submit_pdf` starts a new run. |

Access is unchanged: `require_role("teacher", "administrator")` plus `scope.taught_offering_ids` (section ignored). Admin upload remains `POST /admin/topics/{id}/generation-runs`. Deprecated `POST /teaching/subtopics/{id}/lesson-proposals` is **410**.

## HTTP (thin)

Teaching (teacher + admin, offering-scoped):

- `GET /teaching/generation-runs/{run_id}` — run + review board
- `GET /teaching/topics/{topic_id}/generation-runs`
- `PUT /teaching/generation-runs/{run_id}/overlay` — upsert **my** draft
- `POST /teaching/generation-runs/{run_id}/review` — seal overlay with stance
- `POST /teaching/generation-runs/{run_id}/chat/messages` — generation-review graph
- `POST /teaching/generation-runs/{run_id}/revision-asks` — post-publish only

Admin closer (administrator principal):

- `POST /teaching/generation-runs/{run_id}/collate`
- `POST /teaching/generation-runs/{run_id}/merge`
- `POST /teaching/generation-runs/{run_id}/seal-round` — expire now; pending → abstain
- existing `accept-outline`, `discard`, `retry`, `reject-items`, `publish`

Gone:

- `PATCH /teaching/generation-runs/{run_id}/outline` → 410
- `POST /teaching/subtopics/{id}/lesson-proposals` → 410

## Worker

Same process as ingest. Outline success opens **outline** review round 1 against the frozen node list; it does not wait for a teacher PATCH. Items + lesson success opens **qa** review round 1 against section rows (one per outline node) and draft items. New job kind `collate` writes a `ProposedMerge` onto the round; it does not touch the DAG, SMV, or quiz. Worker never writes `published` / `released`.

---

## Call site 1 — teacher outline review

`/teacher/topics/:topicId/generation` (today's `GenerationRunsPage` + `TopicGenerationReview`). Teachers do not upload. They poll one run, edit **their** overlay, submit a stance. Other teachers' sealed diffs render like a review list (author, node, before/after). Chat sits beside the DAG.

```tsx
// frontend/src/pages/teacher/GenerationRunsPage.tsx
import {
  getGenerationRun,
  pollGenerationRun,
  putGenerationOverlay,
  submitGenerationReview,
  postGenerationReviewChat,
} from "../../api/generation";

const run = await pollGenerationRun(runId);
// run.phase === "outline_review"
// run.review.round.index === 1
// run.outline is read-only base; run.review.my_overlay is the draft

await putGenerationOverlay(run.id, {
  base_fingerprint: run.review.round.base_fingerprint,
  body: {
    stage: "outline",
    node_ops: [
      { kind: "edit", node_id: nodeId, title: "Linear equations, one unknown" },
      { kind: "comment", node_id: nodeId, body: "Keep this as the opener." },
    ],
  },
});

await submitGenerationReview(run.id, { stance: "request_changes" });
// Shared nodes are still the outline-job base. Admin sees this teacher's diff.

await postGenerationReviewChat(run.id, {
  content: "Draft a request-changes op that splits the quadratic node.",
});
// Returns assistant text plus optional suggested ops; it does not write the overlay.
```

Admin buttons (`accept`, `discard`) stay hidden here. Teacher Approve is `submitGenerationReview({ stance: "approve" })`, not `acceptGenerationOutline`.

---

## Call site 2 — admin merge board

`/admin/topics/:topicId` (today's admin materials detail + upload). Admin still uploads the PDF and is the only closer. The board lists each roster teacher, effective stance, and the derived diff. Collate is optional. Merge is the DAG write. Accept still match-or-creates live `Subtopic` / `LearningOutcome` and enqueues items+lesson — **after** overlays are merged or overridden, not when a teacher saves.

```tsx
// frontend/src/pages/admin/AdminMaterialsTopicDetailPage.tsx
import {
  applyGenerationMerge,
  collateGenerationOverlays,
  acceptGenerationOutline,
  discardGenerationRun,
  sealGenerationRound,
  submitTopicGenerationRun,
} from "../../api/generation";

await submitTopicGenerationRun(topicId, file, title, 80);

const run = await getGenerationRun(runId);
// run.review.roster_progress = { submitted: 2, abstained: 1, pending: 1, size: 4 }
// run.review.visible_diffs[i].teacher_user_id + ops

await sealGenerationRound(run.id); // pending → abstain; drafts stay attributed but not request_changes
await collateGenerationOverlays(run.id);
// poll until run.review.proposed_merge is set (job kind=collate)

await applyGenerationMerge(run.id, run.review.proposed_merge);
// Round 1 sealed as merged; round 2 opens with a new base_fingerprint.
// If this was already round 2, no round 3 — accept or discard next.

await acceptGenerationOutline(run.id);
// Remaining pending teachers abstain. Curriculum writes happen here, not at overlay save.
```

If every sealed stance is Approve or Abstain, admin may skip collate and `acceptGenerationOutline` on the current base (override / closer). `discardGenerationRun` remains admin-only; legal from `outline_review`, `failed`, and `qa_review`.

---

## Call site 3 — QA overlays, then locked publish

Same round machine after generate. Overlay anchors are outline-node ids (lesson sections) and question ids (items). Admin publish is the only student-visible write. After publish, overlays are illegal; a teacher may only ask for a **new run**.

```tsx
// frontend/src/components/TopicGenerationQa.tsx
import {
  putGenerationOverlay,
  submitGenerationReview,
  publishGenerationRun,
  askGenerationRevision,
} from "../../api/generation";

// phase === "qa_review", review.stage === "qa", round 1 of 2
await putGenerationOverlay(run.id, {
  base_fingerprint: run.review.round.base_fingerprint,
  body: {
    stage: "qa",
    section_ops: [{ kind: "comment", node_id: sectionNodeId, body: "Worked example is off-source." }],
    item_ops: [{ kind: "reject", question_id: questionId, body: "Two correct options." }],
  },
});
await submitGenerationReview(run.id, { stance: "request_changes" });

// Admin closer may collate, apply_merge (rewrites draft sections / archives rejected items),
// then publishGenerationRun(run.id). Worker still does not publish.

// phase === "published" — student GET /topics/{id}/material unchanged; no keys.
await askGenerationRevision(run.id, {
  reason: "Board changed the fractions sequence; need a new PDF run.",
});
// 409 if you PUT overlay on a published run. Admin submit_pdf starts the next in-flight run.
```

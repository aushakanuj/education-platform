# Frozen-revision generation review

Generation review behaves like a pull request. A run exposes one frozen revision and one open teacher round at a time. Teachers either approve that exact revision or submit attributed change requests anchored to its outline nodes, lesson sections, or quiz items. They never edit the shared DAG or generated content in place.

The first outline job creates outline revision 1 and teacher round 1. An administrator may accept it, discard the run, or close the round for one collated AI rewrite. The rewrite creates revision 2 and teacher round 2. After round 2, the administrator must accept the current revision, supply an explicit frozen override and accept it, or discard. The generated lesson and quiz use the same two-round process.

Silence is visible as `pending` before the deadline and `abstained` after it. It never counts as approval. Only an administrator closes a round. Workers may create the next draft revision, but never accept or publish.

Published revisions are locked. Teachers can read their review history but cannot add post-publish requests. A later change starts a new run through the existing administrator PDF upload flow; the one-in-flight-run-per-topic rule still applies.

## HTTP quickstart

The administrator upload contract stays unchanged:

```http
POST /admin/topics/0f81.../generation-runs
Content-Type: multipart/form-data

title=Linear equations
target_item_count=70
file=@linear-equations.pdf
```

Poll the existing run endpoint until `phase` is `outline_review`, then load the review workspace:

```http
GET /teaching/generation-runs/4af2.../review
```

The workspace is the complete review-page read model: active frozen revision, parent-to-current diff, open round and deadline, snapshotted reviewer roster, attributed submissions, and each change request beside the target as it appeared in that revision. In outline review, the snapshot contains the DAG. In content review, it contains lesson sections and staff-only quiz items, including answer keys. This response is available only on teaching routes.

## Call site 1: teacher review panel

The UI keeps edits local until the teacher submits one immutable decision. A stale tab cannot comment on a newer revision because both the round and revision are named in the command.

```ts
const workspace = await getGenerationReview(runId);
const round = workspace.open_round;
if (!round || workspace.active_revision.stage !== "outline") return;

await submitReviewDecision(runId, round.id, {
  revision_id: workspace.active_revision.id,
  verdict: "changes_requested",
  requests: [
    {
      target: { kind: "outline_node", node_key: selectedNode.node_key },
      field: "proposed_outcomes",
      kind: "curriculum_alignment",
      comment: "Add an outcome that checks solving equations with variables on both sides.",
    },
  ],
});
```

Approval uses the other member of the decision union, so an approval cannot accidentally carry unresolved requests:

```ts
await submitReviewDecision(runId, round.id, {
  revision_id: workspace.active_revision.id,
  verdict: "approve",
});
```

The server obtains `author_user_id` from the JWT, checks an active teaching assignment for the topic's offering, stamps `submitted_at`, and permits one decision per reviewer per round. A duplicate returns `409`; the submitted review remains part of history.

## Call site 2: teacher assistant drafts a request

The assistant is scoped to the frozen revision currently on screen. Its suggestion is only a local draft; posting a chat turn cannot alter a review decision or revision.

```ts
const reply = await askGenerationAssistant(runId, {
  revision_id: workspace.active_revision.id,
  target: { kind: "outline_node", node_key: selectedNode.node_key },
  message: "Explain why this outcome may be too broad and draft a precise request.",
});

if (reply.draft_change_request) {
  setDraftRequest(reply.draft_change_request);
}
```

For content review the same call accepts a `lesson_section` or `quiz_item` target. The generation assistant retrieves only the run's frozen snapshot and intake-source evidence. Policy chat remains at `/admin/policy/chats` with its existing handbook strategy.

## Call site 3: administrator closes the round

After inspecting approvals, requests, and abstentions, the administrator chooses one close action. In teacher round 1, requests can be collated into exactly one rewrite job:

```http
POST /teaching/generation-runs/4af2.../review-rounds/c391.../close
Content-Type: application/json

{
  "revision_id": "b247...",
  "action": "rewrite"
}
```

The response is `202 Accepted`. The worker reads the frozen revision plus the submitted request IDs captured by the close command and creates revision 2 in one bounded model call. It also creates teacher round 2. It does not publish.

At either round, the administrator may accept the current revision:

```ts
await closeReviewRound(runId, round.id, {
  revision_id: workspace.active_revision.id,
  action: "accept_current",
});
```

Accepting an outline materializes the approved subtopics/outcomes and queues lesson and quiz generation. Accepting content publishes the selected lesson and quiz versions in the administrator request transaction. The student material and quiz APIs remain unchanged, and their schemas never include answer keys or review data.

After teacher round 2, `rewrite` is invalid. If requests still need resolution, the administrator can submit `override_and_accept` with a complete replacement snapshot and a rationale. The service stores it as a new frozen, attributed revision, computes the final diff, and accepts that revision atomically; it never mutates revision 2.

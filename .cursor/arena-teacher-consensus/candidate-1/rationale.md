## Problem

The existing generation run already owns admin PDF intake, worker jobs, outline review, generated lesson/quiz QA, and admin publication, but its outline is a shared mutable DAG and its generated content has no review history. Multiple offering-assigned teachers now need to review one school-wide curriculum without overwriting each other, while every request remains attributable and an administrator remains the only closer. The design must preserve the existing run and one-in-flight-topic rule, defer writes to live curriculum until acceptance, keep workers from publishing, keep answer keys off student APIs, and add generation chat without coupling it to the admin policy assistant's handbook retrieval graph.

## Usage (caller's view)

An administrator continues to upload with `POST /admin/topics/{topic_id}/generation-runs` and poll the run to `outline_review`. A teacher then loads one complete review page with `GET /teaching/generation-runs/{run_id}/review` and submits exactly one immutable `approve` or `changes_requested` decision against the returned round and revision. The latter contains one or more typed requests such as `{target: outline_node, field: proposed_outcomes, kind: curriculum_alignment, comment: ...}`; identity and time come from the server.

The adjacent chat posts the same revision and optional target to `POST /teaching/generation-runs/{run_id}/assistant/turns`. It returns an explanation and optionally a typed request draft, but cannot submit it. An administrator closes a round through one command: rewrite, accept current, override-and-accept, or discard. Round 1 rewrite queues one worker job and yields frozen revision 2 plus teacher round 2. Round 2 cannot rewrite again. Accepting outline queues generation; accepting content publishes. Full examples are in `usage.md`.

## Shape

The core data is an immutable `OutlineRevision` or `ContentRevision` attached to a `GenerationRun`. Stable target keys survive between snapshots, while each revision owns complete node, section, and quiz-item snapshots. This makes snapshot-to-snapshot diff and request-to-reviewed-target display direct domain operations rather than audit-log reconstruction, per data-structures-first. Revision constructors validate DAG closure, key uniqueness, item limits, answer-key consistency, and stage-specific content. An administrator override creates another attributed snapshot and accepts it atomically; no route mutates a frozen revision.

Teacher state is per actor: an immutable decision is unique by `(round, reviewer)`, and its change requests carry author, target, field, structured kind, comment, and timestamp. The reviewer roster is snapshotted from active offering-scoped teaching assignments only to show pending/abstained participation; current authorization is still checked on every command. Review reads merge these decisions at the boundary. A separate immutable close record freezes the exact request IDs selected for collation, per shared-state discipline. Silence projects to abstention at deadline/close, round numbers can only be 1 or 2, and an administrator may always accept, override, or discard, so teacher inactivity cannot deadlock the run.

The deep public service has three operations: get workspace, submit teacher decision, and close round. It hides authorization, roster resolution, stale-revision rejection, deadlines, collation, successor uniqueness, materialization, job creation, and publication, per information hiding. The HTTP interface mirrors those capabilities instead of exposing load/validate/save stages. Internal revision code owns both validation and diffing because both depend on stable identity and snapshot rules; separating them into temporal pipeline modules would leak the representation.

A unique successor per parent makes each stage a linear frozen history and removes a mutable “current revision” pointer. The worker receives a frozen rewrite plan, makes at most one model call, copies untouched content, validates a complete successor, and opens the next round. It may create drafts but has no accept/publish capability. On outline acceptance, the service materializes subtopics and outcomes; on content acceptance, the administrator transaction writes the selected lesson and quiz to the existing published models. Teaching DTOs can contain quiz keys, while student serializers never import review snapshot types, per boundary discipline.

Assistant orchestration dispatches on a typed context to `PolicyAssistantStrategy` or `GenerationReviewStrategy`; both receive the shared `core.llm` gateway. Policy routes and handbook retrieval remain unchanged. The generation strategy authorizes the run and loads only the named frozen revision, target, and intake evidence. It has no mutating tools. This keeps graph/retrieval knowledge behind strategies rather than creating a second LLM stack or passing policy-specific state through generation callers.

The interface is deep relative to its size: four client calls cover the review workspace, decision submission, administrative closure, and assistant turn, while hiding the concurrency and lifecycle machinery. The exposed revision, target, decision, and close-action unions are product concepts the UI must render, not storage schemas or worker protocol. No pass-through repository is public, and stage dispatch stays inside revision/rewrite services rather than forcing callers to coordinate outline and content implementations.

## Synthesis decision

Orchestrator fills after arena.

## Tradeoffs accepted

- We accept complete immutable snapshots and additional storage in exchange for deterministic history, stable diffs, and no reconstruction from mutable rows.
- We accept one final administrator decision even after unanimous teacher approval in exchange for preserving the explicit admin-closer and publish boundary.
- We accept immutable submitted decisions, with local editing before submit, in exchange for simple attribution and no ambiguity about which request set a rewrite consumed.
- We accept a full staff-only content workspace that may be larger than the current run response in exchange for reviewing lesson and quiz as one publishable revision; pagination can remain an HTTP projection without changing the domain snapshot.
- We accept locking published revisions and requiring a new admin-uploaded run for later changes in exchange for a clear student-visible boundary and unchanged one-in-flight semantics.
- We accept no silent retry of a failed collated rewrite in exchange for enforcing the one-model-call bound and making admin override/discard explicit.

## Alternatives considered

- **Shared live PATCH plus an audit log:** rejected because it gives callers a shallow edit API while exposing sequencing and optimistic-concurrency rules, permits teachers to overwrite one another, and requires reconstructing “what was reviewed” from logs. It hides little and leaks mutable DAG semantics into every caller.
- **Per-teacher overlays merged by the administrator:** rejected for this candidate because it makes isolation excellent but exposes overlay lifecycle, conflict resolution, and merge previews to the admin UI. Frozen request threads preserve per-teacher ownership while the service hides one collation operation behind a smaller close interface.
- **Event-sourced field patches as the source of truth:** rejected because replay, schema evolution, node creation/deletion ordering, and content-key changes become caller-visible concepts. It stores less than full snapshots but makes historical reads and diffs shallower and more coupled to implementation details.
- **Automatic quorum or unanimous-approval advancement:** rejected because silence and changing assignment rosters make the transition policy surprising, and it weakens the required administrator-closer boundary. Explicit close with projected abstentions hides more timing complexity from teacher callers.

## Open questions and risks

- What default review duration should set `closes_at`, and should institutions be allowed to configure it?
- Should an administrator be allowed to close before the deadline without an explicit confirmation that pending teachers will be recorded as abstained?
- Should a failed one-call rewrite permit an administrator-triggered second call with a new close record, or must resolution remain manual override/discard?
- Can the first implementation send all 60–80 staff quiz snapshots in one workspace response, or should the HTTP read model paginate items while retaining one complete domain revision?
- What editor should produce a complete validated admin override without encouraging the old live-PATCH interaction model?
- Is “published is locked until an administrator uploads a new run” the intended long-term policy, or will a later feature add a teacher-authored proposal that an administrator converts into a new run?

## Next implementation step

Add the revision, round, participant, decision, request, and close-record tables plus domain constructors before replacing the current mutable outline PATCH.

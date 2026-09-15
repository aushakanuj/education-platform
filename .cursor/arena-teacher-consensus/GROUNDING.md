# Grounding: teacher–admin consensus on topic generation

Traced 2026-09-13 from working tree on `feature/material_generation`. Not a recap of HANDOFF; this is what the code does.

## What already exists

- `GenerationRun` stored phase machine: indexing → outlining → outline_review → generating → qa_review → published (plus failed/discarded).
- One in-flight run per topic. Admin `POST /admin/topics/{id}/generation-runs` uploads PDF. Ingest indexes chunks (teacher+admin roles, not students). Outline job proposes nodes. PATCH mutates the shared DAG in place. Admin accept freezes quotas, match-or-creates live `Subtopic`/`LearningOutcome`, enqueues items+lesson. Admin QA + publish writes topic `slug=lesson` and releases `topic_mastery`.
- Teachers of the offering: GET run, PATCH outline. Admin closer: accept, discard, retry, reject-items, publish.
- Draft lesson lives on the run (`draft_lesson_markdown`). Student lesson is a different SMV. Keys only on teaching GET QA items.
- Policy assistant: admin-only `/chats*`, hardcoded LangGraph inject→validate→retrieve→summarize. Tool registry exists but the model does not choose tools. LLM client is already shared (`core.llm`). Generation was designed without a second LangGraph.
- Directory unlocks topic quiz when published topic lesson exists.

## What does not exist

- ChangeRequest, outline revision/history, review round, round limit, attributed actor on PATCH.
- Optimistic concurrency / If-Match on outline.
- Teacher approve vs request-changes (only live PATCH).
- Collation job or “AI rewrite from teacher comments.”
- Generation chatbot. `/teacher/assistant` is an ask-the-data stub.
- Post-publish teacher change-request on the student lesson/quiz.
- Discard from `generating` / `qa_review`.
- Demo teacher JWT on Demo School (admin+student only).

## Constraints the next design must honor

- One curriculum per topic. Students all see the same published lesson and topic quiz. No per-teacher student lessons.
- Admin uploads PDF. Teachers do not (close the deprecated lesson-proposal POST).
- Access = roles + teaching assignments / enrollments. Offering-level (section is ignored for generation). No new grant types.
- Worker never publishes. Student APIs never expose answer keys.
- Postgres + existing worker claim loop. No Redis/Kafka/MinIO. Markdown in Postgres.
- Do not reuse `awaiting_approval` SMV as outline_review.
- Accept today writes live Subtopics before generate — a consensus design should freeze curriculum later or keep drafts separate until admin closer.
- `PATCH` cannot add node IDs; only the outline job mints them.

## Callers that must keep working

- Admin topic upload + poll to outline_review.
- Student `GET /topics/{id}/material` and directory `has_topic_lesson`.
- Subtopic admin ingest (index-only).
- Policy assistant `/admin/policy` unchanged for handbook chat.

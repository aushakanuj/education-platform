# Handoff: topic-grain content generation

Use this file as the start of a new Agent chat. Full types: `candidate-1/shape.md` plus `synthesized/shape.md`. Do not treat `LessonProposal` as the destination.

## Product rules (agreed in chat after the architect sketch)

- **Admin uploads the PDF** (admin UI / existing admin materials ingest). Not teacher UI.
- **One central curriculum per topic** (Grade–Subject). Students all study the same published lesson and the same `topic_mastery` quiz. Teachers teach that; they do not each publish a private student lesson.
- **One generation run per topic** (in-flight unique on the topic), not per teacher.
- **Outline HITL is shared:** assigned teachers of that offering can view/edit the outline and request changes. **A designated closer accepts** (administrator, or “no open change-requests”). Do **not** build unanimous voting or majority ballots in v1.
- **Markdown lives in Postgres** (`content_markdown` / run draft text), same as seeded lessons. `docs/curriculum/*.md` is seed-only. PDF blobs stay on disk (`UPLOAD_DIR`).
- Admin **READY** stays index-only. Worker never auto-publishes. Student APIs never expose answer keys.
- Access = roles + teaching assignments / enrollments. No new grant types.
- No Redis/Kafka, OpenSearch/Chroma, MinIO, second generative microservice, or LangGraph for this flow.

## Architecture (synthesized)

`GenerationRun` is the workflow aggregate. Intake PDF = topic-scoped `source_materials` slug `source` → Docling → **READY**. Outline nodes on the run until accept, then match-or-create `Subtopic` + `LearningOutcome`. Student topic `slug=lesson` + released `topic_mastery` only at HITL 2 publish.

Slice 1 HTTP (adjust submit to **admin**, not `POST /teaching/topics/...` as the product upload):

- Admin enqueue on a **topic** (extend admin materials UI; do not use teacher lesson-proposals as the destination).
- GET/list/patch outline, accept, discard, retry (outline failure must not fail a READY PDF).
- Deprecated: `POST /teaching/subtopics/{id}/lesson-proposals` is leftover intake, not the product.

`complete_from_chunks` is deleted. `ingest_jobs` stay index-only; `generation_jobs` own outline LLM. `IngestTargetKind` does not grow.

## Status (2026-09-09)

Slice 1 backend is in the repo. Do not re-implement it.

**Done.** `generation/` module, Alembic `content_generation_runs` / outline nodes / `generation_jobs`, topic XOR on `source_materials`, admin `POST /admin/topics/{topic_id}/generation-runs`, teaching GET/list/PATCH/accept/discard/retry, deprecated lesson-proposal POST as topic alias (old GET/LIST 410), ingest hook `on_intake_indexed`, outline job only, accept parks at `generating` with `jobs: []`. Admin topic page has `TopicGenerationUpload` (submit + poll to outline_review / failed / generating). Subtopic `POST /admin/subtopics/{id}/materials` stays index-only.

**Not done.** Item bank, student lesson, publish, `GET /topics/{id}/material`, directory unlock, teacher outline editor, QA UI, admin accept/discard from the browser.

## Implementation slices

1. **Done.** Schema + admin topic upload + index-then-outline + shared outline GET/PATCH + accept/discard/retry. No 60–80 items, no topic lesson, no voting.
2. Structured items + quotas (tagged `subtopic_id` + outcomes).
3. One topic lesson in Postgres markdown. Section-wise teach rewrite (below), then stitch. Mermaid retry. Not a one-shot summary of the PDF.
4. QA publish (admin closer); student `GET /topics/{id}/material`; directory unlock from published topic lesson.
5. UI: admin upload (partial) + run status through QA; teacher outline review/edit (and later QA). Browser-verify.

## Remaining work (do in this order)

0. **Done.** Slice 3 teaching rules are in this file and grafted in `synthesized/shape.md`. They override `write_topic_lesson` as a single dump of all chunks.
1. **Admin HITL 1 in the UI.** Topic page (or a run page) can PATCH the outline and accept / discard / retry. Without this, slice 1 is curl-only after upload.
2. **Slice 2.** On accept, enqueue `generation_jobs(kind=items)`. Find-or-create DRAFT `topic_mastery`. Per frozen node, generate that node's quota from **that heading's chunks**. Tag `subtopic_id` + outcomes. Bloom mix as in `candidate-1/shape.md`. Rationales only on `question_answer_keys`. Never `released`. Worker never publishes.
3. **Slice 3.** Enqueue `kind=lesson`. Sequential section writers + stitch (spec below). Store `draft_lesson_markdown`. Students still see seeded lessons until slice 4.
4. **Slice 4.** Admin closer: QA draft lesson + item table, `reject_items`, `publish` (topic `slug=lesson` published markdown, release `topic_mastery`, bind). `GET /topics/{id}/material`. Directory unlocks topic quiz from that lesson when it exists; else keep pass-all-subtopic-quizzes. Seeded leaf lessons stay.
5. **Slice 5 remainder.** Teacher outline editor (no teacher upload). Admin run status through `qa_review` / `published`. QA table. Browser-verify the full loop.

**Done when.** A student opens one topic lesson that teaches in outline order, in plain language, with worked problems, then a 60–80 item topic quiz, from an admin-uploaded PDF that a human accepted twice (outline, then QA).

### Slice 3 lesson authoring

The intake PDF is the fact base (definitions, numbers, tables). The student lesson is a **teach rewrite** for the grade, not a shortened PDF.

Generate **in outline `sequence`**, one section per accepted node, from that node's chunks (and neighbors if needed). Do not generate sections in parallel with an empty prompt. Do not send the whole PDF in one call.

Each section prompt includes:

- A topic card: grade voice, glossary (same word for the same idea for the whole run).
- A short carry-forward brief: what earlier sections already taught, which words are already defined, what not to repeat.
- The teaching template: plain-language idea, why it matters, one diagram or Mermaid, a worked example grounded in the source chunks, a try-it problem, common mistakes, a short recap.

After sections exist, a thin stitch pass writes only 2–3 sentence bridges and one topic recap. It does not rewrite the teaching. Concatenate into `draft_lesson_markdown`.

If one section still overflows the model window, split that section (idea pass, then examples pass). Do not shrink it into a blurb.

HITL 2 still required. Default model output without this template is a summary; do not ship that.

`candidate-1/shape.md` `write_topic_lesson` stays the persistence signature (one markdown string on the run). Internally it is sequential section jobs or a single worker that loops nodes in order. Mermaid parse/retry stays.

## Out of scope

Voting, teacher-owned private lessons, LangGraph for this flow, MinIO, Redis/Kafka, new grant types, student grounded tutor, deleting the PDF after ingest.

## Pointers

| File | What |
| --- | --- |
| `synthesized/usage.md` | Caller usage (still shows teacher submit — **override**: admin upload) |
| `synthesized/shape.md` | Grafts (discard, retry, directory unlock, slice 3 section-wise lesson) |
| `synthesized/rationale.md` | Why GenerationRun |
| `candidate-1/shape.md` | Full type sketch |
| `SYNTHESIS.md` | Arena pick/graft record |
| `GROUNDING.md` | Constraints from existing ingest/proposals/quizzes |
| `docs/research/EdTech Content Pipeline Architecture.md` | Product destination (adapt to this repo) |

## New-chat starter

Continue topic-grain generation from `.cursor/arena-topic-generation/HANDOFF.md` **Remaining work**. Slice 1 backend is done; do not rebuild it. Next: admin HITL 1 UI if you need a demo, then slice 2 items, then slice 3 using the lesson authoring spec (not a one-shot PDF summary). Follow synthesized GenerationRun + grafts. Add tests. Run the backend quality gate (`uv` from `backend/`). Browser-verify any UI.

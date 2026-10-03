# Shape (synthesized grafts)

Start from [candidate-1/shape.md](../candidate-1/shape.md). This file only records grafts onto that type sketch. Implementers treat both as one contract.

## Slice 1 HTTP surface (after graft)

`submit_pdf`, `get_run`, `list_runs`, `patch_outline`, `accept_outline`, `discard_outline`, `retry_failed`.

Still no generate HTTP. PATCH still **replaces** the outline document (no KEEP/DROP/MATCH/CREATE opcodes).

## `discard_outline`

Legal from `outline_review` and `failed`. Phase → `discarded`. Outline nodes may remain for audit or be deleted; they must not be accepted later. In-flight unique clears (`discarded` is terminal). Live `Subtopic` rows unchanged (none were written unless a previous accepted run exists). Intake SMV stays READY or FAILED. Idempotent if already `discarded`.

Illegal while `indexing` / `outlining` / `generating` / `qa_review` / `published` (409). Post-accept abandon is a later slice (`discard` from `generating`/`qa_review` archives unpublished products and **keeps** accepted subtopics).

## `retry_failed`

Legal only when `phase is failed` **and** intake is READY (outline/generation job died). Re-enqueue `generation_jobs(kind=outline)` (slice 1) or the failed kind later. Phase → `outlining`. Same run id.

If intake is FAILED, 409: caller must `submit_pdf` again.

## Index vs outline failure

`fail_run_for_intake` may set the version FAILED. `_finish_outline` on exception: run FAILED, job FAILED, **intake stays READY**.

## Slice 1 park

`accept_outline` still moves to `generating` without enqueueing item/lesson jobs. GET should expose that no generation jobs are queued so the UI does not wait for `qa_review`.

## Slice 3 lesson (graft)

`write_topic_lesson` still persists one `draft_lesson_markdown` on the run. It does **not** mean one LLM call over all chunks.

Generate in outline `sequence`. Each accepted node: that heading's chunks, a topic glossary/voice card, a carry-forward brief from earlier sections, then the teaching template (plain language, worked example from the source, try-it, common mistakes, recap). Stitch pass writes bridges only. Mermaid parse/retry unchanged. Full product text: [../HANDOFF.md](../HANDOFF.md) (Slice 3 lesson authoring).

## Slice 4 directory (spec only)

`published_topic_material_version(topic_id)`. If present, topic quiz unlocks from the published topic lesson, not from passing every subtopic quiz. Topics without a published generation lesson keep the seeded gate. Do not create an empty topic `lesson` SMV at accept.

## Provenance (later, not the aggregate)

Optional `generated_from_version_id` on published lesson / question versions pointing at the intake PDF. The run id remains the workflow key.

## Do not take from candidate-2

Hangar `open_intake_version_id` on `source_materials`; `ingest_jobs.phase`; `subtopic_revisions` as HITL 1; derived `TopicGenerationPhase`; empty lesson version at accept.

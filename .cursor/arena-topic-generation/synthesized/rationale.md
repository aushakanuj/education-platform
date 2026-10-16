# Rationale

## Problem

Teachers must turn a topic PDF into one student lesson plus a 60–80 item `topic_mastery` bank, with two human gates, without any of that becoming student-visible until publish. The unreleased `LessonProposal` stretches `SourceMaterialVersion` (`id == version.id`, `awaiting_approval`, subtopic slug `"lesson"`, ~5 questions). Product moved the grain to **topic**, outline HITL before expensive gen, items as diagnostic tags. SMV cannot name outline, item bank, or two interrupts; `READY` already means indexed. Admin ingest, student directory, and seeded catalogs must keep working. No LangGraph, no new `IngestTargetKind` that still points at SMV, no second student-visibility table.

## Usage (caller's view)

A teacher calls `submit_pdf` on a **topic** and polls `get_run` until `outline_review` or `failed`. HITL 1 is `patch_outline` (replace the run-local DAG) then `accept_outline` (quotas + match-or-create). If the outline is wrong, `discard_outline` clears the topic. If the outline job died and the PDF is READY, `retry_failed` re-enqueues outline on the same run. There is no generate HTTP: accept is the resume. Slice 1 parks at `generating` without item jobs. Later, the same `get_run` grows a QA table; `publish` writes student copies. Call sites: teacher inbox, ingest hook `on_intake_indexed` plus `generation_jobs` in the same worker, thin `/teaching/topics/{id}/generation-runs*`. Deprecated POST `/teaching/subtopics/{id}/lesson-proposals` resolves the parent topic. Full README: [usage.md](usage.md).

## Shape

**`GenerationRun` is the workflow aggregate.** Phase, outline, later draft markdown, later draft quiz version, and FKs to intake / published copies hang off `content_generation_runs`. Intake PDF is topic-scoped `slug="source"` → **READY**, unpublished. Outline nodes are `content_generation_outline_nodes` until accept. Student `slug="lesson"` SMV and released `topic_mastery` exist only after HITL 2.

`ingest_jobs` stay “parse this SMV.” `generation_jobs` (SKIP LOCKED, ingest first in the same worker) own outline and later LLM. After READY, `on_intake_indexed` is a no-op for admin and, for a run in `indexing`, enqueues `kind=outline` in the same commit. Index failure may fail the PDF **and** the run. Outline failure fails the run and the job only.

Slice 1 HTTP: `submit`, `get`, `list`, `patch`, `accept`, `discard`, `retry`. PATCH replaces the outline document. Quotas are derived until accept freezes integers. `ItemCount` encodes 60–80.

Interface depth: those operations hide blob, XOR parent, in-flight lock, Docling, outline LLM/heuristic, match, Largest Remainder, and curriculum writes. Exposed: `RunPhase` (async poll) and the outline document (HITL 1). Per boundary-discipline, `UploadFile` and LLM JSON stay behind the interface.

## Synthesis decision

Base: candidate-1 (GenerationRun). Cross-judge [f791392a](f791392a-326a-4acd-9db5-a844bc0968f7) and parent agreed. Grafted from candidate-2: artifact-vs-job failure, slice-1 discard, slice-1 retry on READY intake, slice-4 directory unlock spec. Rejected: hangar mutex, ingest pipeline phase, revision-as-HITL-doc, opcode PATCH, derived phase, empty lesson SMV at accept. Record: [../SYNTHESIS.md](../SYNTHESIS.md).

## Tradeoffs accepted

- We accept a run table that is never student-visible in exchange for not stretching SMV into a second “is this the lesson?” switch.
- We accept `generation_jobs` in slice 1 (outline) in exchange for keeping `ingest_jobs` index-only.
- We accept parking at `generating` with zero jobs in slice 1 in exchange for a stable `accept_outline` signature when slice 2 enqueues.
- We accept discard + retry in slice 1 (slightly larger surface than C1’s five calls) in exchange for not trapping a topic in `outline_review` / `failed` with no recovery except re-upload after a unique that still blocked.
- We accept a heading-skeleton outline when OpenRouter is missing in exchange for a demoable HITL 1.
- We accept JSON `proposed_outcomes` on the node in exchange for not creating an outcomes child table for 1–3 draft strings.
- We accept flat `subtopics` (no `parent_subtopic_id`) in exchange for not migrating seeded trees. DAG lives on the run.
- We accept leaving `awaiting_approval` in the SMV enum (unused by this flow) in exchange for not rewriting leftover CHECKs in the same Alembic as XOR.

## Alternatives considered

**Stretch `SourceMaterialVersion` (slug `"lesson"`, `awaiting_approval`).** Rejected. Wrong grain; `READY`+markdown collides with admin indexed; product just left this shape.

**Curriculum-rows-as-workflow (`subtopic_revisions` are HITL 1; no run).** Rejected as the base. Acceptable as a loser: topic-as-id looks smaller until phase is derived from lock + jobs + revisions + two SMVs, and until an empty lesson version exists before QA. Discarded runs must not be the academic tree; a run-local node table writes curriculum once, on accept.

**Hang outline LLM off `ingest_jobs` after READY.** Rejected. Mixes Docling failure with generation; admin path learns generation policy.

**New `IngestTargetKind` pointing at SMV or the run.** Rejected. `target_kind` is which table `target_id` points at.

**LangGraph checkpointer.** Rejected. The run row plus claim tables are the checkpoint.

## Open questions and risks

- On match, refuse to rewrite seeded subtopic name/sequence. If the teacher renames a matched node, should accept update the curriculum row?
- `on_intake_indexed` in the READY commit still loses if the process dies after RUNNING (existing stuck-job problem). Sweep `indexing`+READY runs at poll start?
- Dual-role users remain unrestricted admins. Correct when generation writes curriculum rows?
- Slice 1 parks at `generating` with no jobs. Document in GET payload (`jobs: []`) so the UI does not spinner-wait for QA.

## Next implementation step

Alembic for `content_generation_runs`, `content_generation_outline_nodes`, `generation_jobs`, and `source_materials` topic XOR; then `submit_pdf` + ingest hook that enqueues outline; delete `complete_from_chunks`.

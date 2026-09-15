# Synthesized design: topic-grain generation

Base: [candidate-1](candidate-1/shape.md). Cross-judge: [f791392a](f791392a-326a-4acd-9db5-a844bc0968f7). Parent agreed.

## Synthesis decision

Candidate-1 is the base. `GenerationRun` is the workflow aggregate. Teachers poll `run_id`. Intake PDF is topic-scoped `slug=source`, Docling to **READY** only. Outline nodes are run children until accept, then match-or-create `Subtopic` + `LearningOutcome`. Student `slug=lesson` + released `topic_mastery` exist only at HITL 2 publish. `ingest_jobs` stay index-only; `generation_jobs` own outline (and later LLM). `IngestTargetKind` does not grow. `complete_from_chunks` is deleted.

Grafted from candidate-2:

- **Artifact vs job failure.** Index may mark the PDF `FAILED`. Outline (and later items/lesson) failure must not. Intake stays READY; run → `failed`.
- **`discard_outline` in slice 1.** From `outline_review` or `failed`: drop run-local nodes, phase `discarded`, in-flight unique clears, live curriculum untouched, intake stays READY.
- **`retry_failed` in slice 1** when intake is READY (outline died): same run, re-enqueue `kind=outline`, phase `outlining`. No re-upload required.
- **Directory unlock (slice 4 spec, not slice 1 code).** Published topic lesson unlocks `topic_mastery`; seeded topics without that lesson keep “pass all subtopic quizzes.” Leaf seeded lessons stay.

Rejected from candidate-2: hangar mutex on `source_materials`; `ingest_jobs.phase` as pipeline; `subtopic_revisions` as the HITL document; opcode PATCH; derived phase; empty topic `lesson` SMV at accept; wide slice-1 HTTP (reopen, abandon, intakes list, separate QA GET).

## Rubric scores (parent)

| Criterion | C1 | C2 |
| --- | --- | --- |
| Product grain | 5 | 4 |
| Student isolation | 5 | 4 |
| Interface depth | 5 | 3 |
| Invariants | 5 | 3 |
| Repo fit | 4 | 3 |
| Slice 1 startability | 4 | 3 |

C2 red flags: shallow opcode/verb surface, pipeline leaked onto ingest rows, temporal job-phase model, empty lesson SMV at accept.

## Verification

Both candidates honor topic grain, READY index-only, worker never publishes, student published/released, no LangGraph/Redis/MinIO. C1 alone keeps a stored phase, a small poll surface, and student tables untouched until publish. Grafts close C1’s slice-1 hole (outline_review occupying the topic with no discard/retry).

Implementers read [synthesized/](synthesized/) as the contract. Candidate folders stay for the record.

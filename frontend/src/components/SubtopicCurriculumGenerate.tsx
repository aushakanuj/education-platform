import { useEffect, useRef, useState } from "react";

import {
  enqueueCurriculumGeneration,
  isInFlightCurriculumGenerationStatus,
  isTerminalCurriculumGenerationStatus,
  pollCurriculumGenerationJob,
} from "../api/generation";
import { ApiError, type CurriculumGenerationJob, type CurriculumGenerationStatus } from "../api/types";
import type { AdminSubtopic } from "../lib/adminCurriculumLive";
import { PushButton } from "./PushButton";

function jobStatusLabel(status: CurriculumGenerationStatus): string {
  switch (status) {
    case "queued":
      return "Queued";
    case "running":
      return "Generating";
    case "succeeded":
      return "Generated";
    case "failed":
      return "Failed";
    default: {
      const _never: never = status;
      return _never;
    }
  }
}

function JobStatusBadge({ status }: { status: CurriculumGenerationStatus }) {
  switch (status) {
    case "queued":
    case "running":
      return <span className="badge badge--info">{jobStatusLabel(status)}</span>;
    case "succeeded":
      return <span className="badge badge--ok">{jobStatusLabel(status)}</span>;
    case "failed":
      return <span className="badge badge--warn">{jobStatusLabel(status)}</span>;
    default: {
      const _never: never = status;
      return _never;
    }
  }
}

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

function SubtopicGenerateRow({
  subtopic,
  onSucceeded,
}: {
  subtopic: AdminSubtopic;
  onSucceeded: () => void;
}) {
  const [job, setJob] = useState<CurriculumGenerationJob | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      pollAbortRef.current?.abort();
    };
  }, []);

  async function onGenerate() {
    if (busy) return;
    setBusy(true);
    setError(null);

    pollAbortRef.current?.abort();
    const abort = new AbortController();
    pollAbortRef.current = abort;

    try {
      const accepted = await enqueueCurriculumGeneration(subtopic.id);
      if (abort.signal.aborted) return;
      setJob(accepted);
      const settled = isTerminalCurriculumGenerationStatus(accepted.status)
        ? accepted
        : await pollCurriculumGenerationJob(accepted.id, {
            signal: abort.signal,
            onUpdate: setJob,
          });
      if (abort.signal.aborted) return;
      setJob(settled);
      if (settled.status === "succeeded") {
        onSucceeded();
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      setError(errorMessage(err, "Could not generate the lesson and quiz."));
    } finally {
      if (!abort.signal.aborted) setBusy(false);
    }
  }

  const lessonMeta = subtopic.lesson ? "Published lesson" : null;
  const quizMeta = subtopic.quiz ? subtopic.quiz.title : null;
  const meta = [lessonMeta, quizMeta].filter(Boolean).join(" · ");
  const inFlight = job ? isInFlightCurriculumGenerationStatus(job.status) : false;

  return (
    <li className="list-item list-item--with-actions">
      <span className="list-item__num">{String(subtopic.order).padStart(2, "0")}</span>
      <div>
        <p className="list-item__title">{subtopic.title}</p>
        {meta ? <p className="list-item__meta">{meta}</p> : null}
        {job ? (
          <div className="admin-generate__status" role="status">
            <JobStatusBadge status={job.status} />
            {job.round_count > 0 ? (
              <span className="admin-generate__rounds">
                {job.round_count === 1 ? "1 review round" : `${job.round_count} review rounds`}
              </span>
            ) : null}
            {job.reviewer_notes ? (
              <p className="admin-generate__notes">{job.reviewer_notes}</p>
            ) : null}
            {job.status === "failed" && job.error ? (
              <p className="form__error">{job.error}</p>
            ) : null}
          </div>
        ) : null}
        {error ? (
          <p className="form__error" role="alert">
            {error}
          </p>
        ) : null}
      </div>
      <div className="list-item__actions">
        <PushButton
          size="sm"
          variant="outline"
          disabled={busy || inFlight}
          loading={busy || inFlight}
          onClick={() => void onGenerate()}
        >
          {busy || inFlight ? "Generating…" : "Generate lesson & quiz"}
        </PushButton>
      </div>
    </li>
  );
}

type SubtopicCurriculumGenerateListProps = {
  subtopics: AdminSubtopic[];
  onSucceeded: () => void;
};

export function SubtopicCurriculumGenerateList({
  subtopics,
  onSucceeded,
}: SubtopicCurriculumGenerateListProps) {
  return (
    <section className="panel admin-generate" aria-labelledby="admin-generate-heading">
      <h2 id="admin-generate-heading" className="admin-generate__title">
        Generate lesson & quiz
      </h2>
      <p className="admin-generate__lede">
        Requires a curriculum PDF uploaded and ingested for the subtopic first. Generation fails
        if there are no indexed chunks.
      </p>
      {subtopics.length === 0 ? (
        <p className="muted">No subtopics in this topic.</p>
      ) : (
        <ul className="list">
          {subtopics.map((subtopic) => (
            <SubtopicGenerateRow
              key={subtopic.id}
              subtopic={subtopic}
              onSucceeded={onSucceeded}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

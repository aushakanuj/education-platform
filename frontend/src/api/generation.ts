import { apiRequest } from "./client";
import { runSubject, watchProgress } from "./progress";
import type {
  AcceptedGenerationRun,
  CloseRoundCommand,
  CloseRoundResult,
  CurriculumGenerationJob,
  CurriculumGenerationStatus,
  GenerationAssistantReply,
  GenerationAssistantTurn,
  GenerationRun,
  PublishedTopic,
  ReviewWorkspace,
  RunPhase,
  TeacherDecision,
  TeacherDecisionCommand,
} from "./types";

export const CURRICULUM_GENERATION_POLL_MS = 1500;

export function isInFlightGenerationPhase(phase: RunPhase): boolean {
  switch (phase) {
    case "indexing":
    case "outlining":
    case "outline_review":
    case "generating":
    case "qa_review":
      return true;
    case "failed":
    case "discarded":
    case "published":
      return false;
    default: {
      const _never: never = phase;
      void _never;
      return false;
    }
  }
}

export function isInFlightCurriculumGenerationStatus(
  status: CurriculumGenerationStatus,
): boolean {
  switch (status) {
    case "queued":
    case "running":
      return true;
    case "succeeded":
    case "failed":
      return false;
    default: {
      const _never: never = status;
      void _never;
      return false;
    }
  }
}

export function isTerminalCurriculumGenerationStatus(
  status: CurriculumGenerationStatus,
): boolean {
  return !isInFlightCurriculumGenerationStatus(status);
}

function waitForPoll(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const onAbort = () => {
      window.clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    const timer = window.setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

export async function enqueueCurriculumGeneration(
  subtopicId: string,
): Promise<CurriculumGenerationJob> {
  return apiRequest<CurriculumGenerationJob>(
    `/admin/subtopics/${encodeURIComponent(subtopicId)}/generate-curriculum`,
    { method: "POST" },
  );
}

export async function getCurriculumGenerationJob(
  jobId: string,
): Promise<CurriculumGenerationJob> {
  return apiRequest<CurriculumGenerationJob>(
    `/admin/generation-jobs/${encodeURIComponent(jobId)}`,
  );
}

export async function pollCurriculumGenerationJob(
  jobId: string,
  options: {
    signal?: AbortSignal;
    intervalMs?: number;
    onUpdate?: (job: CurriculumGenerationJob) => void;
  } = {},
): Promise<CurriculumGenerationJob> {
  const intervalMs = options.intervalMs ?? CURRICULUM_GENERATION_POLL_MS;
  while (!options.signal?.aborted) {
    const job = await getCurriculumGenerationJob(jobId);
    options.onUpdate?.(job);
    if (isTerminalCurriculumGenerationStatus(job.status)) {
      return job;
    }
    await waitForPoll(intervalMs, options.signal);
  }
  throw new DOMException("Aborted", "AbortError");
}

export function isTerminalGenerationPhase(phase: RunPhase): boolean {
  switch (phase) {
    case "indexing":
    case "outlining":
      return false;
    case "outline_review":
    case "failed":
    case "discarded":
    case "generating":
    case "qa_review":
    case "published":
      return true;
    default: {
      const _never: never = phase;
      void _never;
      return false;
    }
  }
}

export async function submitTopicGenerationRun(
  topicId: string,
  file: File,
  title: string,
  targetItemCount?: number,
): Promise<AcceptedGenerationRun> {
  const body = new FormData();
  body.append("file", file);
  body.append("title", title);
  if (targetItemCount != null) {
    body.append("target_item_count", String(targetItemCount));
  }
  return apiRequest<AcceptedGenerationRun>(
    `/admin/topics/${encodeURIComponent(topicId)}/generation-runs`,
    { method: "POST", body },
  );
}

export async function submitSubjectGenerationRun(
  subjectId: string,
  file: File,
  title: string,
  targetItemCount?: number,
): Promise<AcceptedGenerationRun> {
  const body = new FormData();
  body.append("file", file);
  body.append("title", title);
  if (targetItemCount != null) {
    body.append("target_item_count", String(targetItemCount));
  }
  return apiRequest<AcceptedGenerationRun>(
    `/admin/subjects/${encodeURIComponent(subjectId)}/generation-runs`,
    { method: "POST", body },
  );
}

export async function getGenerationRun(runId: string): Promise<GenerationRun> {
  return apiRequest<GenerationRun>(`/teaching/generation-runs/${encodeURIComponent(runId)}`);
}

export async function listTopicGenerationRuns(topicId: string): Promise<GenerationRun[]> {
  return apiRequest<GenerationRun[]>(
    `/teaching/topics/${encodeURIComponent(topicId)}/generation-runs`,
  );
}

export async function getGenerationReview(runId: string): Promise<ReviewWorkspace> {
  return apiRequest<ReviewWorkspace>(
    `/teaching/generation-runs/${encodeURIComponent(runId)}/review`,
  );
}

export async function submitReviewDecision(
  runId: string,
  roundId: string,
  command: TeacherDecisionCommand,
): Promise<TeacherDecision> {
  return apiRequest<TeacherDecision>(
    `/teaching/generation-runs/${encodeURIComponent(runId)}/review-rounds/${encodeURIComponent(roundId)}/decisions`,
    { method: "POST", body: command },
  );
}

export async function closeReviewRound(
  runId: string,
  roundId: string,
  command: CloseRoundCommand,
): Promise<CloseRoundResult> {
  return apiRequest<CloseRoundResult>(
    `/teaching/generation-runs/${encodeURIComponent(runId)}/review-rounds/${encodeURIComponent(roundId)}/close`,
    { method: "POST", body: command },
  );
}

export async function askGenerationAssistant(
  runId: string,
  command: GenerationAssistantTurn,
): Promise<GenerationAssistantReply> {
  return apiRequest<GenerationAssistantReply>(
    `/teaching/generation-runs/${encodeURIComponent(runId)}/assistant/turns`,
    { method: "POST", body: command },
  );
}

export async function acceptGenerationOutline(runId: string): Promise<GenerationRun> {
  return apiRequest<GenerationRun>(
    `/teaching/generation-runs/${encodeURIComponent(runId)}/accept-outline`,
    { method: "POST" },
  );
}

export async function discardGenerationRun(runId: string): Promise<GenerationRun> {
  return apiRequest<GenerationRun>(
    `/teaching/generation-runs/${encodeURIComponent(runId)}/discard`,
    { method: "POST" },
  );
}

export async function retryGenerationRun(runId: string): Promise<GenerationRun> {
  return apiRequest<GenerationRun>(
    `/teaching/generation-runs/${encodeURIComponent(runId)}/retry`,
    { method: "POST" },
  );
}

export async function rejectGenerationItems(
  runId: string,
  questionIds: string[],
): Promise<GenerationRun> {
  return apiRequest<GenerationRun>(
    `/teaching/generation-runs/${encodeURIComponent(runId)}/reject-items`,
    { method: "POST", body: { question_ids: questionIds } },
  );
}

export async function publishGenerationRun(runId: string): Promise<PublishedTopic> {
  return apiRequest<PublishedTopic>(
    `/teaching/generation-runs/${encodeURIComponent(runId)}/publish`,
    { method: "POST" },
  );
}

export async function subscribeGenerationRun(
  runId: string,
  options: { signal?: AbortSignal; onSnapshot?: (run: GenerationRun) => void } = {},
): Promise<GenerationRun> {
  const snapshot = await watchProgress(runSubject(runId), {
    signal: options.signal,
    onSnapshot: (next) => {
      options.onSnapshot?.(next as GenerationRun);
    },
  });
  return snapshot as GenerationRun;
}

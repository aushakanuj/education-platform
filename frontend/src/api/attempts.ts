import { apiRequest } from "./client";
import type {
  AttemptHistoryItem,
  AttemptResult,
  StartAttemptResponse,
  SubmitAttemptRequest,
} from "./types";

const startAttemptInflight = new Map<string, Promise<StartAttemptResponse>>();

export async function startAttempt(quizId: string): Promise<StartAttemptResponse> {
  const existing = startAttemptInflight.get(quizId);
  if (existing) return existing;
  const pending = apiRequest<StartAttemptResponse>(
    `/quizzes/${encodeURIComponent(quizId)}/attempts`,
    { method: "POST" },
  ).finally(() => {
    startAttemptInflight.delete(quizId);
  });
  startAttemptInflight.set(quizId, pending);
  return pending;
}

export async function listQuizAttempts(quizId: string): Promise<AttemptHistoryItem[]> {
  return apiRequest<AttemptHistoryItem[]>(
    `/quizzes/${encodeURIComponent(quizId)}/attempts`,
  );
}

export async function submitAttempt(
  attemptId: string,
  payload: SubmitAttemptRequest,
): Promise<AttemptResult> {
  return apiRequest<AttemptResult>(`/attempts/${encodeURIComponent(attemptId)}/submit`, {
    method: "POST",
    body: payload,
  });
}

export async function getAttempt(attemptId: string): Promise<AttemptResult> {
  return apiRequest<AttemptResult>(`/attempts/${encodeURIComponent(attemptId)}`);
}

/** Build the submit payload the API expects. Exported for unit tests. */
export function buildSubmitPayload(
  answers: Record<number, string>,
): SubmitAttemptRequest {
  return {
    answers: Object.entries(answers)
      .map(([question_number, selected_option_label]) => ({
        question_number: Number(question_number),
        selected_option_label,
      }))
      .sort((a, b) => a.question_number - b.question_number),
  };
}

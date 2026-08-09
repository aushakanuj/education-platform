import { apiRequest } from "./client";
import type {
  AttemptResult,
  StartAttemptResponse,
  SubmitAttemptRequest,
} from "./types";

export async function startAttempt(topicId: string): Promise<StartAttemptResponse> {
  return apiRequest<StartAttemptResponse>(
    `/quizzes/${encodeURIComponent(topicId)}/attempts`,
    { method: "POST" },
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

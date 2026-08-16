import type { AttemptHistoryItem, QuizSummary } from "../api/types";

const UNFINISHED = new Set(["in_progress", "abandoned"]);

export function trackedAttempts(attempts: AttemptHistoryItem[]): AttemptHistoryItem[] {
  return attempts.filter((attempt) => attempt.status !== "abandoned");
}

export function quizActionLabel(quiz: QuizSummary | null | undefined): string {
  const hasFinished = Boolean(
    trackedAttempts(quiz?.recent_attempts ?? []).some(
      (attempt) => !UNFINISHED.has(attempt.status),
    ),
  );
  return hasFinished ? "Retake quiz" : "Start quiz";
}

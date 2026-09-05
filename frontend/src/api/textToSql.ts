import { apiRequest } from "./client";

export type Confidence = "high" | "medium" | "low";

export type AskResponse = {
  natural_answer: string;
  confidence: Confidence | null;
  provenance: string | null;
};

/**
 * Single-turn: sends only the current question, never prior turns. There is no history
 * parameter on this function at all, deliberately — the backend graph has no
 * conversation-memory concept (see education_platform.modules.text_to_sql.state), and any
 * thread shown in the UI is a display concern only, built up client-side from independent
 * responses, not something fed back into subsequent requests.
 */
export function askQuestion(question: string): Promise<AskResponse> {
  return apiRequest<AskResponse>("/text-to-sql/ask", {
    method: "POST",
    auth: true,
    body: { question },
  });
}

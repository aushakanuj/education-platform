import { apiRequest } from "./client";

export type AuthorableSubtopic = {
  id: string;
  name: string;
  subject: string;
  topic: string;
  draft_count: number;
  /** Approved questions already in the bank for this subtopic. */
  published_count: number;
};

export type DraftOption = { label: string; text: string };

export type DraftQuestion = {
  id: string;
  prompt: string;
  options: DraftOption[];
  /** Which option is correct. Shown here because this is the review screen. */
  correct_label: string | null;
  explanation: string | null;
  difficulty: string | null;
};

export type GenerationResult = {
  subtopic_id: string;
  subtopic_name: string;
  created: number;
  /** Questions the model produced that failed validation, and why. */
  rejected: string[];
  drafts: DraftQuestion[];
};

export type Difficulty = "easy" | "medium" | "hard";

/** Subtopics the signed-in teacher may write questions for — the subjects they teach. */
export async function fetchAuthorableSubtopics(): Promise<AuthorableSubtopic[]> {
  return apiRequest<AuthorableSubtopic[]>("/authoring/subtopics");
}

export async function fetchDrafts(subtopicId: string): Promise<DraftQuestion[]> {
  return apiRequest<DraftQuestion[]>(`/authoring/subtopics/${subtopicId}/drafts`);
}

/** The approved bank for a subtopic — what this teacher has already said yes to. */
export async function fetchApproved(subtopicId: string): Promise<DraftQuestion[]> {
  return apiRequest<DraftQuestion[]>(`/authoring/subtopics/${subtopicId}/questions`);
}

export async function generateQuestions(
  subtopicId: string,
  count: number,
  difficulty: Difficulty,
): Promise<GenerationResult> {
  return apiRequest<GenerationResult>(`/authoring/subtopics/${subtopicId}/generate`, {
    method: "POST",
    body: { count, difficulty },
  });
}

/** Approve one draft. Deliberately one at a time — a person judges each question. */
export async function publishDraft(versionId: string): Promise<void> {
  await apiRequest<void>(`/authoring/drafts/${versionId}/publish`, { method: "POST" });
}

/** Archive a draft. Kept rather than deleted: what was rejected is worth knowing. */
export async function discardDraft(versionId: string): Promise<void> {
  await apiRequest<void>(`/authoring/drafts/${versionId}`, { method: "DELETE" });
}

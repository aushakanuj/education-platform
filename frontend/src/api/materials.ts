import { apiRequest } from "./client";
import type { LessonMaterial, QuizMaterial, TopicSummary } from "./types";

export async function listTopics(): Promise<TopicSummary[]> {
  return apiRequest<TopicSummary[]>("/materials");
}

export async function getLesson(topicId: string): Promise<LessonMaterial> {
  return apiRequest<LessonMaterial>(`/materials/${encodeURIComponent(topicId)}`);
}

export async function getQuiz(topicId: string): Promise<QuizMaterial> {
  return apiRequest<QuizMaterial>(
    `/materials/${encodeURIComponent(topicId)}/quiz`,
  );
}

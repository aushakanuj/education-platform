import { apiRequest } from "./client";
import type {
  LearningDirectory,
  LessonMaterial,
  MaterialProgress,
  MaterialProgressUpdate,
  QuizMaterial,
} from "./types";

export async function fetchLearningDirectory(): Promise<LearningDirectory> {
  return apiRequest<LearningDirectory>("/me/learning-directory");
}

export async function getSubtopicMaterial(subtopicId: string): Promise<LessonMaterial> {
  return apiRequest<LessonMaterial>(`/subtopics/${encodeURIComponent(subtopicId)}/material`);
}

export async function getSubtopicQuiz(subtopicId: string): Promise<QuizMaterial> {
  return apiRequest<QuizMaterial>(`/subtopics/${encodeURIComponent(subtopicId)}/quiz`);
}

/** Legacy slug path — prefer getSubtopicQuiz; slugs collide across subjects/grades. */
export async function getMaterialQuiz(topicId: string): Promise<QuizMaterial> {
  return apiRequest<QuizMaterial>(`/materials/${encodeURIComponent(topicId)}/quiz`);
}

export async function updateMaterialProgress(
  subtopicId: string,
  payload: MaterialProgressUpdate,
): Promise<MaterialProgress> {
  return apiRequest<MaterialProgress>(
    `/subtopics/${encodeURIComponent(subtopicId)}/material-progress`,
    { method: "PUT", body: payload },
  );
}

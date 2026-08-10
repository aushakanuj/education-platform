import type { AttemptResult, LearningDirectory, StartAttemptResponse } from "../api/types";

export type LearningPath = {
  subjectId: string;
  subjectName: string;
  topicId: string;
  topicTitle: string;
  subtopicId: string | null;
  subtopicTitle: string | null;
  subjectPath: string;
  /** @deprecated Use subjectPath */
  topicPath: string;
  lessonPath: string | null;
  /** Unit lesson page with Quiz tab selected */
  quizTabPath: string | null;
  overallUnlocked: boolean;
  topicComplete: boolean;
};

function pathForTopic(
  subjectId: string,
  subjectName: string,
  topic: LearningDirectory["subjects"][number]["topics"][number],
  subtopic: LearningDirectory["subjects"][number]["topics"][number]["subtopics"][number] | null,
): LearningPath {
  const subjectPath = `/subjects/${subjectId}`;
  const lessonPath = subtopic ? `${subjectPath}/subtopics/${subtopic.id}/lesson` : null;
  return {
    subjectId,
    subjectName,
    topicId: topic.id,
    topicTitle: topic.title,
    subtopicId: subtopic?.id ?? null,
    subtopicTitle: subtopic?.title ?? null,
    subjectPath,
    topicPath: subjectPath,
    lessonPath,
    quizTabPath: lessonPath ? `${lessonPath}?tab=quiz` : null,
    overallUnlocked: Boolean(topic.overall_quiz?.unlocked),
    topicComplete: topic.complete,
  };
}

export function resolveLearningPath(
  directory: LearningDirectory,
  scope: "subtopic_mastery" | "topic_mastery" | null | undefined,
  targetId: string | null | undefined,
): LearningPath | null {
  if (!targetId || !scope) return null;

  for (const subject of directory.subjects) {
    for (const topic of subject.topics) {
      if (scope === "topic_mastery" && topic.id === targetId) {
        return pathForTopic(subject.id, subject.name, topic, null);
      }
      if (scope === "subtopic_mastery") {
        const subtopic = topic.subtopics.find((item) => item.id === targetId);
        if (subtopic) {
          return pathForTopic(subject.id, subject.name, topic, subtopic);
        }
      }
    }
  }
  return null;
}

export function resolvePathFromAttempt(
  directory: LearningDirectory,
  attempt: Pick<StartAttemptResponse | AttemptResult, "scope" | "target_id">,
): LearningPath | null {
  return resolveLearningPath(directory, attempt.scope, attempt.target_id);
}

export function resolvePathFromQuizId(
  directory: LearningDirectory,
  quizId: string,
): LearningPath | null {
  for (const subject of directory.subjects) {
    for (const topic of subject.topics) {
      if (topic.overall_quiz?.id === quizId) {
        return pathForTopic(subject.id, subject.name, topic, null);
      }
      for (const subtopic of topic.subtopics) {
        if (subtopic.quiz?.id === quizId) {
          return pathForTopic(subject.id, subject.name, topic, subtopic);
        }
      }
    }
  }
  return null;
}

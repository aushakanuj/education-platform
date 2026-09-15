import type { LearningDirectory, SubjectNode, SubtopicNode, TopicNode } from "../api/types";

/** POC school curriculum lives in the first (and usually only) published topic bucket. */
export function schoolTopic(subject: SubjectNode): TopicNode | null {
  return subject.topics[0] ?? null;
}

export function subjectSubtopics(subject: SubjectNode) {
  return subject.topics.flatMap((topic) => topic.subtopics);
}

export type SubjectUnitEntry = {
  topic: TopicNode;
  subtopic: SubtopicNode | null;
};

function publishedLessonSubtopics(topic: TopicNode): SubtopicNode[] {
  return topic.subtopics.filter((subtopic) => subtopic.has_lesson);
}

/** Same grain as the student Units list: published subtopic lessons, or the topic when none exist. */
export function subjectUnitEntries(topics: TopicNode[]): SubjectUnitEntry[] {
  const entries: SubjectUnitEntry[] = [];
  for (const topic of topics) {
    const lessonUnits = publishedLessonSubtopics(topic);
    if (lessonUnits.length > 0) {
      for (const subtopic of lessonUnits) {
        entries.push({ topic, subtopic });
      }
      continue;
    }
    entries.push({ topic, subtopic: null });
  }
  return entries;
}

export function subjectTopicLessonTopics(topics: TopicNode[]): TopicNode[] {
  return topics.filter(
    (topic) => hasPublishedTopicLesson(topic) && publishedLessonSubtopics(topic).length > 0,
  );
}

export function subjectProgress(subject: SubjectNode): {
  done: number;
  total: number;
  pct: number;
} {
  const subtopics = subjectSubtopics(subject);
  const total = subtopics.length;
  const done = subtopics.filter((item) => item.progress_percent === 100).length;
  return {
    done,
    total,
    pct: total === 0 ? 0 : Math.round(subject.progress_percent),
  };
}

export function topicLessonPath(subjectId: string, topicId: string): string {
  return `/subjects/${subjectId}/topics/${topicId}/lesson`;
}

export function hasPublishedTopicLesson(topic: TopicNode): boolean {
  return Boolean(topic.has_topic_lesson);
}

export function findSubjectTopic(
  directory: LearningDirectory,
  subjectId: string,
  topicId: string,
): { subject: SubjectNode; topic: TopicNode } | null {
  const subject = directory.subjects.find((item) => item.id === subjectId);
  const topic = subject?.topics.find((item) => item.id === topicId);
  if (!subject || !topic) return null;
  return { subject, topic };
}

export type OverallQuizGate = "topic_lesson" | "subtopic_quizzes";

export function overallQuizGate(topic: TopicNode): OverallQuizGate {
  return hasPublishedTopicLesson(topic) ? "topic_lesson" : "subtopic_quizzes";
}

export type OverallQuizCopy = {
  eyebrow: string;
  statusLine: string;
  body: string;
};

export function overallQuizCopy(topic: TopicNode): OverallQuizCopy {
  const quiz = topic.overall_quiz;
  const gate = overallQuizGate(topic);
  const unlocked = Boolean(quiz?.unlocked);
  const passed = Boolean(quiz?.passed);

  switch (gate) {
    case "topic_lesson":
      return {
        eyebrow: "From the topic lesson",
        statusLine: unlocked
          ? passed
            ? "Passed · subject complete"
            : "Unlocked · ready to take"
          : "Locked until the topic lesson is published",
        body: unlocked
          ? passed
            ? "You passed the overall topic quiz."
            : "The topic lesson is published. You can take the overall quiz now."
          : "The overall quiz unlocks when the topic lesson is published.",
      };
    case "subtopic_quizzes":
      return {
        eyebrow: "After all units",
        statusLine: unlocked
          ? passed
            ? "Passed · subject complete"
            : "Unlocked · ready to take"
          : "Locked until every unit quiz is passed",
        body: unlocked
          ? passed
            ? "You passed the overall topic quiz."
            : "All unit quizzes passed. You can take the overall subject quiz."
          : "Finish every unit quiz to unlock this subject quiz.",
      };
    default: {
      const _exhaustive: never = gate;
      return _exhaustive;
    }
  }
}

import type { SubjectNode, TopicNode } from "../api/types";

/** POC school curriculum lives in the first (and usually only) published topic bucket. */
export function schoolTopic(subject: SubjectNode): TopicNode | null {
  return subject.topics[0] ?? null;
}

export function subjectSubtopics(subject: SubjectNode) {
  return subject.topics.flatMap((topic) => topic.subtopics);
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

import { Link } from "react-router-dom";

import type { AttemptHistoryItem, MaterialProgress, QuizSummary, SubtopicNode, TopicNode } from "../api/types";
import { trackedAttempts } from "../lib/quizAction";
import {
  hasPublishedTopicLesson,
  subjectTopicLessonTopics,
  subjectUnitEntries,
  topicLessonPath,
} from "../lib/subjectMaterial";
import { formatAttemptWhen } from "./AttemptHistory";

function lessonStarted(progress: MaterialProgress | null | undefined, progressPercent: number): boolean {
  return progress?.status === "opened" || progress?.status === "completed" || progressPercent > 0;
}

function unitStatus(
  lessonDone: boolean,
  quiz: QuizSummary | null,
  progress: MaterialProgress | null | undefined,
  progressPercent: number,
): {
  label: string;
  cls: string;
} {
  if (quiz?.passed) return { label: "Quiz passed", cls: "badge--ok" };
  if (lessonDone && quiz?.unlocked) return { label: "Quiz unlocked", cls: "badge--info" };
  if (lessonDone) return { label: "Lesson done", cls: "badge--info" };
  if (lessonStarted(progress, progressPercent)) return { label: "In progress", cls: "badge--warn" };
  return { label: "Not started", cls: "badge--locked" };
}

function QuizAttemptResult({ attempt }: { attempt: AttemptHistoryItem }) {
  const score =
    attempt.score_percent == null ? null : `${Math.round(Number(attempt.score_percent))}%`;

  if (attempt.status === "in_progress" || attempt.status === "abandoned") {
    return <span className="quiz-meta">Not finished</span>;
  }
  if (attempt.passed === true) {
    return (
      <span className="quiz-meta quiz-meta--ok">
        Passed{score ? ` · ${score}` : ""}
      </span>
    );
  }
  if (attempt.passed === false) {
    return (
      <span className="quiz-meta quiz-meta--fail">
        Not passed{score ? ` · ${score}` : ""}
      </span>
    );
  }
  return <span className="quiz-meta">{attempt.status.replaceAll("_", " ")}</span>;
}

function UnitQuizMeta({ quiz }: { quiz: QuizSummary | null }) {
  if (!quiz?.available) return null;

  if (quiz.in_progress_attempt_id) {
    return <p className="subtopic-card__quiz-meta">Unfinished · start again</p>;
  }
  if (!quiz.unlocked) {
    return <p className="subtopic-card__quiz-meta">Complete lesson to unlock</p>;
  }

  const latest = trackedAttempts(quiz.recent_attempts)[0];
  if (!latest) {
    return <p className="subtopic-card__quiz-meta">Ready to take</p>;
  }

  const when = formatAttemptWhen(latest);
  return (
    <p className="subtopic-card__quiz-meta">
      {when ? <>Last quiz {when} · </> : "Last quiz · "}
      <QuizAttemptResult attempt={latest} />
    </p>
  );
}

function SubtopicUnitCard({
  subjectId,
  subtopic,
  index,
}: {
  subjectId: string;
  subtopic: SubtopicNode;
  index: number;
}) {
  const status = unitStatus(
    subtopic.lesson_completed,
    subtopic.quiz,
    subtopic.progress,
    subtopic.progress_percent,
  );

  return (
    <li className="subtopic-card">
      <Link to={`/subjects/${subjectId}/subtopics/${subtopic.id}/lesson`} className="subtopic-card__head">
        <div className="list-item__num">{String(index + 1).padStart(2, "0")}</div>
        <div>
          <p className="list-item__title">{subtopic.title}</p>
          <p className="list-item__meta">{Math.round(subtopic.progress_percent)}% complete</p>
        </div>
        <div className="subtopic-card__quiz-col">
          <span className={`badge ${status.cls}`}>{status.label}</span>
          <UnitQuizMeta quiz={subtopic.quiz} />
        </div>
        <span className="subtopic-card__chevron" aria-hidden="true">
          ›
        </span>
      </Link>
    </li>
  );
}

function TopicUnitCard({
  subjectId,
  topic,
  index,
}: {
  subjectId: string;
  topic: TopicNode;
  index: number;
}) {
  const quiz = topic.overall_quiz;
  const lessonDone = Boolean(topic.topic_lesson_completed);
  const status = unitStatus(lessonDone, quiz, null, topic.progress_percent);

  return (
    <li className="subtopic-card">
      <Link to={topicLessonPath(subjectId, topic.id)} className="subtopic-card__head">
        <div className="list-item__num">{String(index + 1).padStart(2, "0")}</div>
        <div>
          <p className="list-item__title">{topic.title}</p>
          <p className="list-item__meta">{Math.round(topic.progress_percent)}% complete</p>
        </div>
        <div className="subtopic-card__quiz-col">
          <span className={`badge ${status.cls}`}>{status.label}</span>
          <UnitQuizMeta quiz={quiz} />
        </div>
        <span className="subtopic-card__chevron" aria-hidden="true">
          ›
        </span>
      </Link>
    </li>
  );
}

export function SchoolMaterialPanel({
  subjectId,
  topics,
}: {
  subjectId: string;
  subjectName: string;
  topics: TopicNode[];
}) {
  const topicLessons = subjectTopicLessonTopics(topics);
  const units = subjectUnitEntries(topics);

  return (
    <div className="topic-layout">
      <div className="topic-layout__main">
        <div className="school-material-stack">
          {topicLessons.map((topic) => (
            <section
              key={topic.id}
              className="school-section school-section--topic-lesson"
              aria-labelledby={`topic-lesson-heading-${topic.id}`}
            >
              <header className="school-section__head">
                <div>
                  <p className="school-section__eyebrow">Topic lesson</p>
                  <h2 id={`topic-lesson-heading-${topic.id}`}>{topic.title}</h2>
                  <p>Published lesson that covers this subject.</p>
                </div>
                {hasPublishedTopicLesson(topic) ? (
                  <span className="badge badge--ok">published</span>
                ) : null}
              </header>
              <p className="topic-lesson-card__copy">
                Open the topic lesson slides, then take the overall quiz when it unlocks.
              </p>
              <div className="topic-lesson-card__actions">
                <Link to={topicLessonPath(subjectId, topic.id)} className="btn btn--sm">
                  Open topic lesson
                </Link>
              </div>
            </section>
          ))}

          <section className="school-section school-section--units" aria-labelledby="units-heading">
            <header className="school-section__head">
              <h2 id="units-heading">Units</h2>
              <p>Work through each unit lesson and quiz.</p>
            </header>
            {units.length === 0 ? (
              <p className="muted">No units published for this subject yet.</p>
            ) : (
              <ul className="list">
                {units.map((entry, index) =>
                  entry.subtopic ? (
                    <SubtopicUnitCard
                      key={entry.subtopic.id}
                      subjectId={subjectId}
                      subtopic={entry.subtopic}
                      index={index}
                    />
                  ) : (
                    <TopicUnitCard
                      key={entry.topic.id}
                      subjectId={subjectId}
                      topic={entry.topic}
                      index={index}
                    />
                  ),
                )}
              </ul>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

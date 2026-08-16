import { useState } from "react";
import { Link } from "react-router-dom";

import type { AttemptHistoryItem, MaterialProgress, QuizSummary, TopicNode } from "../api/types";
import { quizActionLabel } from "../lib/quizAction";
import { AttemptHistoryList, AttemptHistoryTrigger, formatAttemptWhen } from "./AttemptHistory";
import { Crumbs } from "./Crumbs";

type Subtopic = TopicNode["subtopics"][number];

function lessonStarted(progress: MaterialProgress | null | undefined, progressPercent: number): boolean {
  return progress?.status === "opened" || progress?.status === "completed" || progressPercent > 0;
}

function subtopicStatus(
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

function SubtopicQuizMeta({ quiz }: { quiz: QuizSummary | null }) {
  if (!quiz?.available) return null;

  if (quiz.in_progress_attempt_id) {
    return <p className="subtopic-card__quiz-meta">Unfinished · start again</p>;
  }
  if (!quiz.unlocked) {
    return <p className="subtopic-card__quiz-meta">Complete lesson to unlock</p>;
  }

  const latest = quiz.recent_attempts[0];
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
  subtopic: Subtopic;
  index: number;
}) {
  const status = subtopicStatus(
    subtopic.lesson_completed,
    subtopic.quiz,
    subtopic.progress,
    subtopic.progress_percent,
  );
  const quiz = subtopic.quiz;

  return (
    <li className="subtopic-card">
      <Link
        to={`/subjects/${subjectId}/subtopics/${subtopic.id}/lesson`}
        className="subtopic-card__head"
      >
        <div className="list-item__num">{String(index + 1).padStart(2, "0")}</div>
        <div>
          <p className="list-item__title">{subtopic.title}</p>
          <p className="list-item__meta">{Math.round(subtopic.progress_percent)}% complete</p>
        </div>
        <div className="subtopic-card__quiz-col">
          <span className={`badge ${status.cls}`}>{status.label}</span>
          <SubtopicQuizMeta quiz={quiz} />
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
  subjectName,
  topic,
}: {
  subjectId: string;
  subjectName: string;
  topic: TopicNode;
}) {
  const [historyView, setHistoryView] = useState<
    null | { scope: "overall" } | { scope: "subtopic"; id: string }
  >(null);

  const historyAttempts =
    historyView?.scope === "overall"
      ? (topic.overall_quiz?.recent_attempts ?? [])
      : historyView?.scope === "subtopic"
        ? (topic.subtopics.find((item) => item.id === historyView.id)?.quiz?.recent_attempts ?? [])
        : [];
  const historyLabel =
    historyView?.scope === "overall"
      ? "Overall quiz attempts"
      : historyView?.scope === "subtopic"
        ? `${
            topic.subtopics.find((item) => item.id === historyView.id)?.title ?? "Subtopic"
          } quiz attempts`
        : "";

  return (
    <div className="topic-layout">
      <div className="topic-layout__main">
        {historyView ? (
          <div className="school-material-stack">
            <Crumbs
              local
              parts={[
                { label: "Units", onClick: () => setHistoryView(null) },
                { label: historyLabel },
              ]}
            />
            <h2 className="school-material-stack__title">{historyLabel}</h2>
            <p className="reading__lede">
              Scores from previous quiz attempts. Open a result for full review.
            </p>
            <AttemptHistoryList attempts={historyAttempts} />
          </div>
        ) : (
          <div className="school-material-stack">
            <section className="school-section school-section--units" aria-labelledby="units-heading">
              <header className="school-section__head">
                <h2 id="units-heading">Units</h2>
                <p>Work through each unit lesson and quiz.</p>
              </header>
              <ul className="list">
                {topic.subtopics.map((subtopic, index) => (
                  <SubtopicUnitCard
                    key={subtopic.id}
                    subjectId={subjectId}
                    subtopic={subtopic}
                    index={index}
                  />
                ))}
              </ul>
            </section>

            {topic.overall_quiz && (
              <section
                className="school-section school-section--subject-quiz"
                aria-labelledby="subject-quiz-heading"
              >
                <header className="school-section__head">
                  <div>
                    <p className="school-section__eyebrow">After all units</p>
                    <h2 id="subject-quiz-heading">{subjectName} quiz</h2>
                    <p>
                      {topic.overall_quiz.unlocked
                        ? topic.overall_quiz.passed
                          ? "Passed · subject complete"
                          : "Unlocked · ready to take"
                        : "Locked until every unit quiz is passed"}
                    </p>
                  </div>
                  <span
                    className={`badge ${
                      topic.overall_quiz.unlocked
                        ? topic.overall_quiz.passed
                          ? "badge--ok"
                          : "badge--info"
                        : "badge--locked"
                    }`}
                  >
                    {topic.overall_quiz.unlocked
                      ? topic.overall_quiz.passed
                        ? "Passed"
                        : "Unlocked"
                      : "Locked"}
                  </span>
                </header>

                <div className="school-subject-quiz__body">
                  <p className="school-subject-quiz__copy">
                    {topic.overall_quiz.unlocked
                      ? "All unit quizzes passed. You can take the overall subject quiz."
                      : "Finish every unit quiz to unlock this subject quiz."}
                  </p>
                  <div className="school-subject-quiz__actions">
                    {topic.overall_quiz.unlocked ? (
                      <Link to={`/quizzes/${topic.overall_quiz.id}`} className="btn btn--sm">
                        {quizActionLabel(topic.overall_quiz).replace("quiz", "subject quiz")}
                      </Link>
                    ) : (
                      <button type="button" className="btn btn--sm" disabled>
                        Start subject quiz
                      </button>
                    )}
                    <AttemptHistoryTrigger
                      title="Subject quiz history"
                      attempts={topic.overall_quiz.recent_attempts}
                      active={historyView?.scope === "overall"}
                      onOpen={() => setHistoryView({ scope: "overall" })}
                    />
                  </div>
                </div>
              </section>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

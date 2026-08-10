import { useState } from "react";
import { Link } from "react-router-dom";

import type { AttemptHistoryItem, MaterialProgress, QuizSummary, TopicNode } from "../api/types";
import { AttemptHistoryList, AttemptHistoryTrigger, formatAttemptWhen } from "./AttemptHistory";
import { PushButton } from "./PushButton";
import { TopicObjectivesRail } from "./TopicObjectivesRail";

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

  if (attempt.status === "in_progress") {
    return <span className="quiz-meta quiz-meta--info">In progress</span>;
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
    return <p className="subtopic-card__quiz-meta">Quiz in progress</p>;
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
  const [objectivesCollapsed, setObjectivesCollapsed] = useState(() => {
    if (typeof window === "undefined") return true;
    try {
      const stored = window.localStorage.getItem("ep.objectivesCollapsed");
      if (stored !== null) return stored === "1";
    } catch {
      /* ignore */
    }
    if (typeof window.matchMedia !== "function") return false;
    return window.matchMedia("(max-width: 1100px)").matches;
  });

  const done = topic.subtopics.filter((s) => s.progress_percent === 100).length;
  const total = topic.subtopics.length;
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
    <div
      className={`topic-layout ${
        topic.objectives.length > 0 ? "topic-layout--with-objectives" : ""
      } ${objectivesCollapsed ? "is-objectives-collapsed" : ""}`}
    >
      <div className="topic-layout__main">
        <div className="panel topic-study-panel">
          <div className="topic-progress">
            <div className="topic-progress__row">
              <p className="progress-label">
                Subject completion · {Math.round(topic.progress_percent)}% · {done}/{total}{" "}
                units · overall quiz {topic.overall_quiz?.passed ? "passed" : "pending"}
              </p>
              {topic.complete ? (
                <span className="badge badge--ok">Complete</span>
              ) : (
                <span className="badge badge--warn">In progress</span>
              )}
            </div>
            <div className="progress" aria-hidden="true">
              <span style={{ width: `${topic.progress_percent}%` }} />
            </div>
          </div>

          {historyView ? (
            <div className="topic-study-panel__content">
              <div className="topic-study-panel__back">
                <PushButton variant="soft" size="sm" onClick={() => setHistoryView(null)}>
                  Back to units
                </PushButton>
              </div>
              <h2 style={{ margin: "0 0 0.35rem", fontSize: "1.1rem" }}>{historyLabel}</h2>
              <p className="reading__lede">
                Scores from previous quiz attempts. Open a result for full review.
              </p>
              <AttemptHistoryList attempts={historyAttempts} />
            </div>
          ) : (
            <div className="topic-study-panel__content">
              <section className="school-section school-section--units" aria-labelledby="units-heading">
                <header className="school-section__head">
                  <h2 id="units-heading">Units</h2>
                  <p>Work through each unit lesson and quiz.</p>
                </header>
                <ul className="list">
                  {topic.subtopics.map((subtopic, index) => {
                    const started = lessonStarted(subtopic.progress, subtopic.progress_percent);
                    const status = subtopicStatus(
                      subtopic.lesson_completed,
                      subtopic.quiz,
                      subtopic.progress,
                      subtopic.progress_percent,
                    );
                    const quiz = subtopic.quiz;
                    return (
                      <li key={subtopic.id} className="subtopic-card">
                        <details className="subtopic-card__details">
                          <summary className="subtopic-card__head">
                            <div className="list-item__num">
                              {String(index + 1).padStart(2, "0")}
                            </div>
                            <div>
                              <p className="list-item__title">{subtopic.title}</p>
                              <p className="list-item__meta">
                                {Math.round(subtopic.progress_percent)}% complete
                              </p>
                            </div>
                            <div className="subtopic-card__quiz-col">
                              <span className={`badge ${status.cls}`}>{status.label}</span>
                              <SubtopicQuizMeta quiz={quiz} />
                            </div>
                            <span className="subtopic-card__chevron" aria-hidden="true">
                              ▾
                            </span>
                          </summary>

                          <div className="subtopic-card__body">
                            <div>
                              <div className="progress-label">
                                Unit progress · {Math.round(subtopic.progress_percent)}%
                              </div>
                              <div className="progress" aria-hidden="true">
                                <span style={{ width: `${subtopic.progress_percent}%` }} />
                              </div>
                            </div>

                            <div className="action-boxes">
                              <div className="action-box">
                                <h3 className="action-box__title">Lesson</h3>
                                <p className="action-box__meta">
                                  {subtopic.lesson_completed
                                    ? "Lesson completed. You can review it anytime."
                                    : started
                                      ? "Lesson in progress. Continue from where you left off."
                                      : "Work through every slide to finish the lesson."}
                                </p>
                                <div className="meta-row">
                                  <span
                                    className={`badge ${
                                      subtopic.lesson_completed
                                        ? "badge--ok"
                                        : started
                                          ? "badge--warn"
                                          : "badge--info"
                                    }`}
                                  >
                                    {subtopic.lesson_completed
                                      ? "Complete"
                                      : started
                                        ? "In progress"
                                        : "Open"}
                                  </span>
                                </div>
                                {subtopic.has_lesson && (
                                  <Link
                                    to={`/subjects/${subjectId}/subtopics/${subtopic.id}/lesson`}
                                    className="btn btn--sm btn--soft"
                                  >
                                    {subtopic.lesson_completed
                                      ? "Review lesson"
                                      : started
                                        ? "Continue lesson"
                                        : "Start lesson"}
                                  </Link>
                                )}
                              </div>

                              <div
                                className={`action-box ${subtopic.lesson_completed ? "" : "is-locked"}`}
                              >
                                <h3 className="action-box__title">Quiz</h3>
                                <p className="action-box__meta">
                                  {subtopic.lesson_completed
                                    ? quiz?.passed
                                      ? "Quiz passed. Retake anytime to practice."
                                      : "Lesson complete. Take the quiz when you are ready."
                                    : "Locked until the lesson is completed."}
                                </p>
                                <div className="meta-row">
                                  <span
                                    className={`badge ${
                                      quiz?.passed
                                        ? "badge--ok"
                                        : subtopic.lesson_completed
                                          ? "badge--info"
                                          : "badge--locked"
                                    }`}
                                  >
                                    {quiz?.passed
                                      ? "Passed"
                                      : subtopic.lesson_completed
                                        ? "Unlocked"
                                        : "Locked"}
                                  </span>
                                </div>
                                {quiz?.available && quiz.unlocked ? (
                                  <Link to={`/quizzes/${quiz.id}`} className="btn btn--sm">
                                    {quiz.recent_attempts.length || quiz.in_progress_attempt_id
                                      ? quiz.in_progress_attempt_id
                                        ? "Resume quiz"
                                        : "Retake quiz"
                                      : "Start quiz"}
                                  </Link>
                                ) : (
                                  <button type="button" className="btn btn--sm" disabled>
                                    Start quiz
                                  </button>
                                )}
                                {!subtopic.lesson_completed && (
                                  <p className="subtopic-card__hint">
                                    Complete the lesson to enable this box.
                                  </p>
                                )}
                                {quiz && (
                                  <AttemptHistoryTrigger
                                    title="Quiz history"
                                    attempts={quiz.recent_attempts}
                                    to={`/subjects/${subjectId}/subtopics/${subtopic.id}/lesson?tab=quiz`}
                                    actionLabel="Open quiz"
                                  />
                                )}
                              </div>
                            </div>
                          </div>
                        </details>
                      </li>
                    );
                  })}
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
                          {topic.overall_quiz.recent_attempts.length
                            ? "Retake subject quiz"
                            : "Start subject quiz"}
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

      <TopicObjectivesRail
        objectives={topic.objectives}
        onCollapsedChange={setObjectivesCollapsed}
      />
    </div>
  );
}

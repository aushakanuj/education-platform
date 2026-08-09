import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { fetchLearningDirectory } from "../api/materials";
import type { MaterialProgress, QuizSummary, TopicNode } from "../api/types";
import { ApiError } from "../api/types";
import { AppShell } from "../components/AppShell";
import { AttemptHistoryList, AttemptHistoryTrigger } from "../components/AttemptHistory";
import { Crumbs } from "../components/Crumbs";
import { PushButton } from "../components/PushButton";

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
  if (lessonStarted(progress, progressPercent)) return { label: "In progress", cls: "badge--info" };
  return { label: "Not started", cls: "badge--locked" };
}

export function TopicPage() {
  const { subjectId = "", topicId = "" } = useParams();
  const [topic, setTopic] = useState<TopicNode | null>(null);
  const [subjectName, setSubjectName] = useState("Subject");
  const [error, setError] = useState<string | null>(null);
  const [historyView, setHistoryView] = useState<null | { scope: "overall" } | { scope: "subtopic"; id: string }>(
    null,
  );

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const directory = await fetchLearningDirectory();
        const subject = directory.subjects.find((item) => item.id === subjectId);
        const found = subject?.topics.find((item) => item.id === topicId) ?? null;
        if (!cancelled) {
          setSubjectName(subject?.name ?? "Subject");
          if (!found) setError("Topic not found in your learning directory.");
          setTopic(found);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Could not load topic.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [subjectId, topicId]);

  const done = topic?.subtopics.filter((s) => s.progress_percent === 100).length ?? 0;
  const total = topic?.subtopics.length ?? 0;
  const historyAttempts =
    historyView?.scope === "overall"
      ? (topic?.overall_quiz?.recent_attempts ?? [])
      : historyView?.scope === "subtopic"
        ? (topic?.subtopics.find((item) => item.id === historyView.id)?.quiz?.recent_attempts ?? [])
        : [];
  const historyLabel =
    historyView?.scope === "overall"
      ? "Overall quiz attempts"
      : historyView?.scope === "subtopic"
        ? `${
            topic?.subtopics.find((item) => item.id === historyView.id)?.title ?? "Subtopic"
          } quiz attempts`
        : "";

  return (
    <AppShell topicTitle={topic?.title}>
      {!topic && !error && (
        <div className="center-state" role="status">
          Loading topic…
        </div>
      )}

      {error && (
        <div className="center-state">
          <p className="form__error" role="alert">
            {error}
          </p>
          <Link to={subjectId ? `/subjects/${subjectId}` : "/"}>
            <PushButton variant="soft">Back to subjects</PushButton>
          </Link>
        </div>
      )}

      {topic && (
        <>
          <Crumbs
            parts={[
              { label: "Subjects", to: "/" },
              { label: subjectName, to: `/subjects/${subjectId}` },
              { label: topic.title },
            ]}
          />
          <div className="back-row">
            <Link to={`/subjects/${subjectId}`} className="btn btn--outline btn--sm">
              ← Back to subject
            </Link>
          </div>

          <header className="page-head">
            <p className="kicker">{historyView ? "Quiz attempts" : "Topic overview"}</p>
            <h1>{topic.title}</h1>
            <p>
              Work through each subtopic lesson, then take its quiz. The overall topic quiz unlocks
              when every subtopic quiz is passed.
            </p>
          </header>

          <div className="panel">
            <div className="progress-label">
              Topic completion · {Math.round(topic.progress_percent)}% · {done}/{total} subtopics ·
              overall quiz {topic.overall_quiz?.passed ? "passed" : "pending"}
            </div>
            <div className="progress" aria-hidden="true">
              <span style={{ width: `${topic.progress_percent}%` }} />
            </div>
            <div className="meta-row" style={{ marginTop: "0.65rem" }}>
              {topic.complete ? (
                <span className="badge badge--ok">Topic complete</span>
              ) : (
                <span className="badge badge--info">In progress</span>
              )}
            </div>
          </div>

          <div className="panel topic-study-panel" style={{ marginTop: "1rem" }}>
            {(topic.overall_quiz || historyView) && (
              <div className="topic-study-panel__quiz">
                {topic.overall_quiz && (
                  <details className="subtopic-card__details">
                  <summary className="subtopic-card__head topic-quiz-panel__head">
                    <div>
                      <p className="list-item__title">Overall topic quiz</p>
                      <p className="list-item__meta">
                        {topic.overall_quiz.unlocked
                          ? topic.overall_quiz.passed
                            ? "Passed · topic complete"
                            : "Unlocked · ready to take"
                          : "Locked until every subtopic quiz is passed"}
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
                    <span className="subtopic-card__chevron" aria-hidden="true">
                      ▾
                    </span>
                  </summary>

                  <div className="subtopic-card__body">
                    <p style={{ margin: 0, color: "var(--ink-muted)", fontSize: "0.95rem" }}>
                      {topic.overall_quiz.unlocked
                        ? "All subtopic quizzes passed. You can take the overall quiz."
                        : "Locked until every subtopic quiz is passed."}
                    </p>
                    <div className="actions">
                      {topic.overall_quiz.unlocked ? (
                        <Link to={`/quizzes/${topic.overall_quiz.id}`} className="btn">
                          {topic.overall_quiz.recent_attempts.length
                            ? "Retake overall quiz"
                            : "Start overall quiz"}
                        </Link>
                      ) : (
                        <button type="button" className="btn" disabled>
                          Start overall quiz
                        </button>
                      )}
                    </div>
                    <AttemptHistoryTrigger
                      title="Overall quiz history"
                      attempts={topic.overall_quiz.recent_attempts}
                      active={historyView?.scope === "overall"}
                      onOpen={() => setHistoryView({ scope: "overall" })}
                    />
                  </div>
                </details>
                )}
                {historyView && (
                  <div className="topic-study-panel__back">
                    <PushButton variant="soft" size="sm" onClick={() => setHistoryView(null)}>
                      Back to topic
                    </PushButton>
                  </div>
                )}
              </div>
            )}

            {historyView ? (
              <div className="topic-study-panel__content">
                <h2 style={{ margin: "0 0 0.35rem", fontSize: "1.1rem" }}>{historyLabel}</h2>
                <p className="reading__lede">
                  Scores from previous quiz attempts. Open a result for full review.
                </p>
                <AttemptHistoryList attempts={historyAttempts} />
              </div>
            ) : (
              <div className="topic-study-panel__content">
                {topic.objectives.length > 0 && (
                  <section className="topic-study-panel__objectives">
                    <h2 style={{ margin: "0 0 0.5rem", fontSize: "1.1rem" }}>Objectives</h2>
                    <ul className="objectives">
                      {topic.objectives.map((objective) => (
                        <li key={objective}>{objective}</li>
                      ))}
                    </ul>
                  </section>
                )}

                <section className="topic-study-panel__subtopics">
                  <h2 style={{ margin: "0 0 0.75rem", fontSize: "1.1rem" }}>Subtopics</h2>
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
                              <span className={`badge ${status.cls}`}>{status.label}</span>
                              <span className="subtopic-card__chevron" aria-hidden="true">
                                ▾
                              </span>
                            </summary>

                            <div className="subtopic-card__body">
                              <div>
                                <div className="progress-label">
                                  Subtopic progress · {Math.round(subtopic.progress_percent)}%
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
                                            ? "badge--info"
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
                                      to={`/subjects/${subjectId}/topics/${topicId}/subtopics/${subtopic.id}/lesson`}
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
                                      active={
                                        historyView?.scope === "subtopic" &&
                                        historyView.id === subtopic.id
                                      }
                                      onOpen={() =>
                                        setHistoryView({ scope: "subtopic", id: subtopic.id })
                                      }
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
              </div>
            )}
          </div>
        </>
      )}
    </AppShell>
  );
}

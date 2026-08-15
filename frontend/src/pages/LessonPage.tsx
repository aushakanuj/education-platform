import { Link } from "react-router-dom";

import { AppShell } from "../components/AppShell";
import { AttemptHistoryTrigger, formatAttempt, formatAttemptWhen } from "../components/AttemptHistory";
import { Crumbs } from "../components/Crumbs";
import { MarkdownContent } from "../components/MarkdownContent";
import { PushButton } from "../components/PushButton";
import { findSummarySlide, useSubtopicLesson } from "../lib/useSubtopicLesson";

export function LessonPage() {
  const {
    lesson,
    subjectName,
    subtopicTitle,
    quizSummary,
    error,
    slides,
    subjectPath,
    lessonPath,
  } = useSubtopicLesson();

  const summarySlide = findSummarySlide(slides);
  const quizUnlocked = Boolean(lesson?.quiz_unlocked && lesson.quiz_id);
  const lessonComplete = Boolean(lesson?.progress?.status === "completed");
  const quizId = lesson?.quiz_id ?? quizSummary?.id ?? null;
  const attempts = quizSummary?.recent_attempts ?? [];
  const latestAttempt = attempts[0] ?? null;
  const quizCta = quizSummary?.in_progress_attempt_id
    ? "Resume quiz"
    : attempts.length > 0
      ? "Retake quiz"
      : "Start quiz";
  const slidesPath = lessonComplete
    ? `${lessonPath}/slides?from=start`
    : `${lessonPath}/slides`;
  const slidesLabel = lessonComplete ? "Review lesson" : "Continue";
  const historyPath = `${lessonPath}/history`;
  const latestWhen = latestAttempt ? formatAttemptWhen(latestAttempt) : null;

  return (
    <AppShell subjectTitle={subjectName}>
      {!lesson && !error && (
        <div className="center-state" role="status">
          Loading lesson…
        </div>
      )}

      {error && (
        <div className="center-state">
          <p className="form__error" role="alert">
            {error}
          </p>
          <Link to={subjectPath}>
            <PushButton variant="matte">Back to units</PushButton>
          </Link>
        </div>
      )}

      {lesson && slides.length > 0 && (
        <div className="lesson-view">
          <Crumbs
            parts={[
              { label: "Subjects", to: "/" },
              { label: subjectName, to: subjectPath },
              { label: subtopicTitle },
            ]}
          />
          <div className="back-row">
            <Link to={subjectPath} className="btn btn--matte btn--sm">
              ← Back to units
            </Link>
          </div>
          <h1 className="sr-only">{subtopicTitle}</h1>

          <div className="lesson-layout">
            <section className="lesson-layout__main" aria-label="Lesson">
              <article className="panel lesson-overview">
                <div className="lesson-overview__header">
                  <h2>{summarySlide?.title ?? "Lesson summary"}</h2>
                </div>
                {summarySlide && (
                  <div className="lesson-overview__scroll markdown">
                    <MarkdownContent>{summarySlide.content}</MarkdownContent>
                  </div>
                )}
                <div className="lesson-overview__footer">
                  <Link to={slidesPath} className="btn">
                    {slidesLabel}
                  </Link>
                </div>
              </article>
            </section>

            <aside className="lesson-layout__aside" aria-label="Quiz history">
              <div className="lesson-quiz-panel">
                <div className="lesson-quiz-panel__hero">
                  <div>
                    <h2 className="lesson-quiz-panel__title">Quiz</h2>
                    <div className="lesson-quiz-panel__meta">
                      {quizSummary?.passed ? (
                        <span className="badge badge--ok">Passed</span>
                      ) : quizUnlocked ? (
                        <span className="badge badge--info">Unlocked</span>
                      ) : (
                        <span className="badge badge--locked">Locked</span>
                      )}
                      <span className="lesson-toolbar__hint">
                        {quizSummary
                          ? `${quizSummary.attempt_count} attempt${quizSummary.attempt_count === 1 ? "" : "s"}`
                          : "No quiz linked"}
                      </span>
                    </div>
                  </div>
                  <div className="lesson-quiz-panel__actions">
                    {quizUnlocked && quizId ? (
                      <Link to={`/quizzes/${quizId}`} className="btn btn--sm">
                        {quizCta}
                      </Link>
                    ) : (
                      <button type="button" className="btn btn--sm" disabled>
                        Start quiz
                      </button>
                    )}
                    {!quizUnlocked && (
                      <p className="lesson-toolbar__hint">Finish every slide to unlock.</p>
                    )}
                  </div>
                </div>

                <div className="lesson-quiz-panel__latest">
                  <h3>Last attempt</h3>
                  {latestAttempt ? (
                    <div className="lesson-quiz-panel__latest-row">
                      <p>
                        <strong>{formatAttempt(latestAttempt)}</strong>
                        {latestWhen && (
                          <span className="lesson-toolbar__hint"> · {latestWhen}</span>
                        )}
                        {quizSummary?.best_score_percent != null && (
                          <span className="lesson-toolbar__hint">
                            {" "}
                            · Best {Math.round(Number(quizSummary.best_score_percent))}%
                          </span>
                        )}
                      </p>
                      <Link to={`/attempts/${latestAttempt.id}`} className="btn btn--soft btn--sm">
                        View attempt
                      </Link>
                    </div>
                  ) : (
                    <p className="lesson-toolbar__hint">No attempts yet.</p>
                  )}
                </div>

                <AttemptHistoryTrigger
                  title="Show full history"
                  attempts={attempts}
                  to={historyPath}
                  actionLabel="Open"
                />
              </div>
            </aside>
          </div>
        </div>
      )}
    </AppShell>
  );
}

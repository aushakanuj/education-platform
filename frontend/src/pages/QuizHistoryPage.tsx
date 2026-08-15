import { Link } from "react-router-dom";

import { AppShell } from "../components/AppShell";
import { AttemptHistoryList } from "../components/AttemptHistory";
import { Crumbs } from "../components/Crumbs";
import { PushButton } from "../components/PushButton";
import { QuizPerformanceChart } from "../components/QuizPerformanceChart";
import { useSubtopicLesson } from "../lib/useSubtopicLesson";

export function QuizHistoryPage() {
  const {
    lesson,
    subjectName,
    subtopicTitle,
    quizSummary,
    error,
    subjectPath,
    lessonPath,
  } = useSubtopicLesson();

  const quizUnlocked = Boolean(lesson?.quiz_unlocked && lesson.quiz_id);
  const quizId = lesson?.quiz_id ?? quizSummary?.id ?? null;
  const attempts = quizSummary?.recent_attempts ?? [];
  const quizCta = quizSummary?.in_progress_attempt_id
    ? "Resume quiz"
    : attempts.length > 0
      ? "Retake quiz"
      : "Start quiz";
  const passThreshold = quizSummary?.pass_threshold_percent ?? 70;

  return (
    <AppShell subjectTitle={subjectName}>
      {!lesson && !error && (
        <div className="center-state" role="status">
          Loading quiz history…
        </div>
      )}

      {error && (
        <div className="center-state">
          <p className="form__error" role="alert">
            {error}
          </p>
          <Link to={lessonPath}>
            <PushButton variant="matte">Back to lesson</PushButton>
          </Link>
        </div>
      )}

      {lesson && (
        <div className="lesson-view">
          <Crumbs
            parts={[
              { label: "Subjects", to: "/" },
              { label: subjectName, to: subjectPath },
              { label: subtopicTitle, to: lessonPath },
              { label: "Quiz history" },
            ]}
          />
          <div className="back-row">
            <Link to={lessonPath} className="btn btn--matte btn--sm">
              ← Back to lesson overview
            </Link>
          </div>

          <div className="quiz-history-page">
            <div className="lesson-quiz-panel">
              <div className="lesson-quiz-panel__hero">
                <div>
                  <h2 className="lesson-quiz-panel__title">Quiz history</h2>
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
                </div>
              </div>

              <QuizPerformanceChart attempts={attempts} passThreshold={passThreshold} />

              <div className="lesson-quiz-panel__history">
                <h3>All attempts</h3>
                <AttemptHistoryList attempts={attempts} />
              </div>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}

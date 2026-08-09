import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { fetchLearningDirectory, getSubtopicMaterial, updateMaterialProgress } from "../api/materials";
import type { LessonMaterial, QuizSummary } from "../api/types";
import { ApiError } from "../api/types";
import { AppShell } from "../components/AppShell";
import { AttemptHistoryList, AttemptHistoryTrigger } from "../components/AttemptHistory";
import { Crumbs } from "../components/Crumbs";
import { MarkdownContent } from "../components/MarkdownContent";
import { PushButton } from "../components/PushButton";

export function LessonPage() {
  const { subjectId = "", topicId = "", subtopicId = "" } = useParams();
  const [lesson, setLesson] = useState<LessonMaterial | null>(null);
  const [topicTitle, setTopicTitle] = useState("Topic");
  const [subjectName, setSubjectName] = useState("Subject");
  const [subtopicTitle, setSubtopicTitle] = useState("Lesson");
  const [subtopicPct, setSubtopicPct] = useState(0);
  const [quizSummary, setQuizSummary] = useState<QuizSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [slideIndex, setSlideIndex] = useState(0);
  const [showHistory, setShowHistory] = useState(false);
  const openedRef = useRef(false);

  const topicPath = `/subjects/${subjectId}/topics/${topicId}`;

  useEffect(() => {
    let cancelled = false;
    openedRef.current = false;
    setLesson(null);
    setError(null);
    setSlideIndex(0);
    setShowHistory(false);
    setQuizSummary(null);
    void (async () => {
      try {
        const [data, directory] = await Promise.all([
          getSubtopicMaterial(subtopicId),
          fetchLearningDirectory(),
        ]);
        if (cancelled) return;
        const subject = directory.subjects.find((item) => item.id === subjectId);
        const topic = subject?.topics.find((item) => item.id === topicId);
        const subtopic = topic?.subtopics.find((item) => item.id === subtopicId);
        setSubjectName(subject?.name ?? "Subject");
        setTopicTitle(topic?.title ?? "Topic");
        setSubtopicTitle(subtopic?.title ?? data.title);
        setSubtopicPct(subtopic?.progress_percent ?? 0);
        setQuizSummary(subtopic?.quiz ?? null);
        setLesson(data);
        if (data.progress?.last_unit_ordinal) {
          setSlideIndex(Math.max(0, data.progress.last_unit_ordinal - 1));
        }
        if (!openedRef.current) {
          openedRef.current = true;
          const progress = await updateMaterialProgress(subtopicId, {
            status: data.progress?.status === "completed" ? "completed" : "opened",
            last_unit_ordinal: data.progress?.last_unit_ordinal ?? 1,
          });
          if (!cancelled) {
            setLesson((prev) => (prev ? { ...prev, progress } : prev));
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Could not load lesson.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [subtopicId, subjectId, topicId]);

  const slides = lesson?.slides ?? [];
  const slide = slides[slideIndex];
  const progressPct =
    slides.length > 0 ? Math.round(((slideIndex + 1) / slides.length) * 100) : 0;
  const atEnd = slides.length > 0 && slideIndex === slides.length - 1;
  const quizUnlocked = Boolean(lesson?.quiz_unlocked && lesson.quiz_id);
  const lessonComplete = Boolean(lesson?.progress?.status === "completed" || atEnd);
  const quizId = lesson?.quiz_id ?? quizSummary?.id ?? null;
  const attempts = quizSummary?.recent_attempts ?? [];
  const quizCta = quizSummary?.in_progress_attempt_id
    ? "Resume quiz"
    : attempts.length > 0
      ? "Retake quiz"
      : "Start subtopic quiz";

  async function markCompleted(unit: number) {
    try {
      const progress = await updateMaterialProgress(subtopicId, {
        status: "completed",
        last_unit_ordinal: unit,
      });
      setLesson((prev) =>
        prev
          ? {
              ...prev,
              progress,
              quiz_unlocked: Boolean(prev.quiz_id) || prev.quiz_unlocked,
            }
          : prev,
      );
      setSubtopicPct((pct) => Math.max(pct, 50));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save lesson progress.");
    }
  }

  async function goNext() {
    if (!lesson || !slides.length) return;
    const next = Math.min(slides.length - 1, slideIndex + 1);
    setSlideIndex(next);
    if (next === slides.length - 1) {
      await markCompleted(slides[next]?.number ?? next + 1);
    } else {
      try {
        const progress = await updateMaterialProgress(subtopicId, {
          status: lesson.progress?.status === "completed" ? "completed" : "opened",
          last_unit_ordinal: slides[next]?.number ?? next + 1,
        });
        setLesson((prev) => (prev ? { ...prev, progress } : prev));
      } catch {
        /* non-blocking */
      }
    }
  }

  return (
    <AppShell topicTitle={topicTitle}>
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
          <Link to={topicPath}>
            <PushButton variant="soft">Back to topic</PushButton>
          </Link>
        </div>
      )}

      {lesson && slide && (
        <div className="lesson-view">
          <Crumbs
            parts={[
              { label: "Subjects", to: "/" },
              { label: subjectName, to: `/subjects/${subjectId}` },
              { label: topicTitle, to: topicPath },
              { label: subtopicTitle },
            ]}
          />
          <div className="back-row">
            <Link to={topicPath} className="btn btn--outline btn--sm">
              ← Back to topic
            </Link>
          </div>

          <header className="page-head">
            <p className="kicker">
              {showHistory
                ? "Quiz attempts"
                : `Subtopic lesson · slide ${slideIndex + 1} of ${slides.length}`}
            </p>
            <h1>{subtopicTitle}</h1>
          </header>

          <div className="lesson-top">
            <section className="lesson-top__panel" aria-label="Lesson progress">
              <h2 className="lesson-top__title">Progress</h2>
              <div className="progress-label">
                Lesson slides · {progressPct}%
                {lessonComplete ? " · lesson complete" : ""}
              </div>
              <div className="progress" aria-hidden="true">
                <span style={{ width: `${progressPct}%` }} />
              </div>
              <div className="progress-label" style={{ marginTop: "0.45rem" }}>
                Subtopic completion · {Math.round(subtopicPct)}%
              </div>
              <div className="progress" aria-hidden="true">
                <span style={{ width: `${subtopicPct}%` }} />
              </div>
              {showHistory && (
                <div className="lesson-top__progress-actions">
                  <PushButton variant="soft" size="sm" onClick={() => setShowHistory(false)}>
                    Continue lesson
                  </PushButton>
                </div>
              )}
            </section>

            <section className="lesson-top__panel" aria-label="Subtopic quiz">
              <h2 className="lesson-top__title">Subtopic quiz</h2>
              <div className="lesson-top__quiz-meta">
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
              <div className="lesson-top__quiz-actions">
                {quizUnlocked && quizId ? (
                  <Link to={`/quizzes/${quizId}`} className="btn btn--sm">
                    {quizCta}
                  </Link>
                ) : (
                  <button type="button" className="btn btn--sm" disabled>
                    Start subtopic quiz
                  </button>
                )}
                {!quizUnlocked && (
                  <p className="lesson-toolbar__hint">Finish every slide to unlock.</p>
                )}
              </div>
              {quizSummary && (
                <div className="lesson-top__history">
                  <AttemptHistoryTrigger
                    title="Quiz attempts"
                    attempts={attempts}
                    active={showHistory}
                    onOpen={() => setShowHistory(true)}
                  />
                </div>
              )}
            </section>
          </div>

          <article className="panel reading">
            {showHistory ? (
              <>
                <div className="reading__header">
                  <h2>Previous attempts</h2>
                  <p className="reading__lede">
                    Scores from your subtopic quiz attempts. Open a result for full review.
                  </p>
                </div>
                <div className="reading__body">
                  <AttemptHistoryList attempts={attempts} />
                </div>
              </>
            ) : (
              <>
                <div className="reading__header">
                  <h2>{slide.title}</h2>
                </div>
                <div className="reading__body markdown">
                  <MarkdownContent>{slide.content}</MarkdownContent>
                </div>
                <div className="reading__footer slide-nav">
                  <PushButton
                    variant="outline"
                    size="sm"
                    disabled={slideIndex === 0}
                    onClick={() => setSlideIndex((i) => Math.max(0, i - 1))}
                  >
                    Previous
                  </PushButton>
                  <PushButton size="sm" disabled={atEnd} onClick={() => void goNext()}>
                    Next slide
                  </PushButton>
                </div>
              </>
            )}
          </article>
        </div>
      )}
    </AppShell>
  );
}

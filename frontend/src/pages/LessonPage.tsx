import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { fetchLearningDirectory, getSubtopicMaterial, updateMaterialProgress } from "../api/materials";
import type { LessonMaterial, LessonSlide, QuizSummary } from "../api/types";
import { ApiError } from "../api/types";
import { AppShell } from "../components/AppShell";
import { AttemptHistoryList, formatAttempt } from "../components/AttemptHistory";
import { Crumbs } from "../components/Crumbs";
import { MarkdownContent } from "../components/MarkdownContent";
import { PushButton } from "../components/PushButton";
import { QuizPerformanceChart } from "../components/QuizPerformanceChart";

type TopTab = "lesson" | "quiz";

function findSummarySlide(slides: LessonSlide[]): LessonSlide | null {
  return slides.find((slide) => /lesson summary/i.test(slide.title)) ?? slides.at(-1) ?? null;
}

function resumeSlideIndex(lesson: LessonMaterial, slides: LessonSlide[]): number {
  const ordinal = lesson.progress?.last_unit_ordinal;
  if (!ordinal || ordinal <= 1) return 0;
  return Math.min(slides.length - 1, ordinal - 1);
}

export function LessonPage() {
  const { subjectId = "", subtopicId = "" } = useParams();
  const [searchParams] = useSearchParams();
  const [lesson, setLesson] = useState<LessonMaterial | null>(null);
  const [subjectName, setSubjectName] = useState("Subject");
  const [subtopicTitle, setSubtopicTitle] = useState("Lesson");
  const [quizSummary, setQuizSummary] = useState<QuizSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [topTab, setTopTab] = useState<TopTab>(() =>
    searchParams.get("tab") === "quiz" ? "quiz" : "lesson",
  );
  const [slideMode, setSlideMode] = useState(false);
  const [slideIndex, setSlideIndex] = useState(0);
  const openedRef = useRef(false);

  const subjectPath = `/subjects/${subjectId}`;

  useEffect(() => {
    setTopTab(searchParams.get("tab") === "quiz" ? "quiz" : "lesson");
  }, [searchParams, subtopicId]);

  useEffect(() => {
    let cancelled = false;
    openedRef.current = false;
    setLesson(null);
    setError(null);
    setSlideMode(false);
    setSlideIndex(0);
    setQuizSummary(null);
    void (async () => {
      try {
        const [data, directory] = await Promise.all([
          getSubtopicMaterial(subtopicId),
          fetchLearningDirectory(),
        ]);
        if (cancelled) return;
        const subject = directory.subjects.find((item) => item.id === subjectId);
        let subtopic = null;
        for (const topic of subject?.topics ?? []) {
          const found = topic.subtopics.find((item) => item.id === subtopicId);
          if (found) {
            subtopic = found;
            break;
          }
        }
        setSubjectName(subject?.name ?? "Subject");
        setSubtopicTitle(subtopic?.title ?? data.title);
        setQuizSummary(subtopic?.quiz ?? null);
        setLesson(data);
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
  }, [subtopicId, subjectId]);

  const slides = lesson?.slides ?? [];
  const summarySlide = findSummarySlide(slides);
  const resumeIndex = lesson ? resumeSlideIndex(lesson, slides) : 0;
  const slide = slides[slideIndex];
  const atEnd = slides.length > 0 && slideIndex === slides.length - 1;
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
  const canResume = resumeIndex > 0;
  const passThreshold = quizSummary?.pass_threshold_percent ?? 70;

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
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save lesson progress.");
    }
  }

  async function persistSlidePosition(index: number) {
    if (!lesson || !slides.length) return;
    const unit = slides[index]?.number ?? index + 1;
    try {
      const progress = await updateMaterialProgress(subtopicId, {
        status:
          lesson.progress?.status === "completed" || index === slides.length - 1
            ? "completed"
            : "opened",
        last_unit_ordinal: unit,
      });
      setLesson((prev) => (prev ? { ...prev, progress } : prev));
    } catch {
      /* non-blocking */
    }
  }

  function openSlides(atIndex: number) {
    setTopTab("lesson");
    setSlideIndex(atIndex);
    setSlideMode(true);
  }

  async function goNext() {
    if (!lesson || !slides.length) return;
    const next = Math.min(slides.length - 1, slideIndex + 1);
    setSlideIndex(next);
    if (next === slides.length - 1) {
      await markCompleted(slides[next]?.number ?? next + 1);
    } else {
      await persistSlidePosition(next);
    }
  }

  function renderTabs() {
    return (
      <div className="lesson-tabs" role="tablist" aria-label="Lesson sections">
        <button
          type="button"
          role="tab"
          id="lesson-tab"
          aria-selected={topTab === "lesson"}
          aria-controls="lesson-tab-panel"
          className={`lesson-tabs__tab ${topTab === "lesson" ? "is-active" : ""}`}
          onClick={() => setTopTab("lesson")}
        >
          Lesson
        </button>
        <button
          type="button"
          role="tab"
          id="quiz-tab"
          aria-selected={topTab === "quiz"}
          aria-controls="quiz-tab-panel"
          className={`lesson-tabs__tab ${topTab === "quiz" ? "is-active" : ""}`}
          onClick={() => setTopTab("quiz")}
        >
          Quiz
        </button>
      </div>
    );
  }

  function renderQuizPanel() {
    return (
      <div
        className="lesson-quiz-panel"
        role="tabpanel"
        id="quiz-tab-panel"
        aria-labelledby="quiz-tab"
      >
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
          <h3>Last quiz</h3>
          {latestAttempt ? (
            <p>
              <strong>{formatAttempt(latestAttempt)}</strong>
              {quizSummary?.best_score_percent != null && (
                <span className="lesson-toolbar__hint">
                  {" "}
                  · Best {Math.round(Number(quizSummary.best_score_percent))}%
                </span>
              )}
            </p>
          ) : (
            <p className="lesson-toolbar__hint">No attempts yet.</p>
          )}
        </div>

        <QuizPerformanceChart attempts={attempts} passThreshold={passThreshold} />

        <div className="lesson-quiz-panel__history">
          <h3>Quiz history</h3>
          <AttemptHistoryList attempts={attempts} />
        </div>
      </div>
    );
  }

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
            <PushButton variant="soft">Back to subject</PushButton>
          </Link>
        </div>
      )}

      {lesson && slides.length > 0 && !slideMode && (
        <div className="lesson-view">
          <Crumbs
            parts={[
              { label: "Subjects", to: "/" },
              { label: subjectName, to: subjectPath },
              { label: subtopicTitle },
            ]}
          />
          <div className="back-row">
            <Link to={subjectPath} className="btn btn--outline btn--sm">
              ← Back to subject
            </Link>
          </div>
          <h1 className="sr-only">{subtopicTitle}</h1>

          <div className="lesson-layout">
            <div className="lesson-layout__main">
              {renderTabs()}

              {topTab === "lesson" ? (
                <div
                  className="lesson-tab-panel"
                  role="tabpanel"
                  id="lesson-tab-panel"
                  aria-labelledby="lesson-tab"
                >
                  <article className="panel lesson-overview">
                    <div className="lesson-overview__header">
                      <div className="lesson-overview__title-row">
                        <h2>{summarySlide?.title ?? "Lesson summary"}</h2>
                        <div className="lesson-overview__actions">
                          {(canResume || lessonComplete) && (
                            <PushButton
                              size="sm"
                              className={lessonComplete ? "btn--complete" : ""}
                              onClick={() =>
                                openSlides(lessonComplete ? 0 : resumeIndex)
                              }
                            >
                              {lessonComplete
                                ? `Complete · ${slides.length}/${slides.length}`
                                : `Continue · ${resumeIndex + 1}/${slides.length}`}
                            </PushButton>
                          )}
                          <PushButton
                            size="sm"
                            variant={canResume || lessonComplete ? "soft" : "primary"}
                            onClick={() => openSlides(0)}
                          >
                            Start from beginning
                          </PushButton>
                        </div>
                      </div>
                    </div>
                    {summarySlide && (
                      <div className="lesson-overview__scroll markdown">
                        <MarkdownContent>{summarySlide.content}</MarkdownContent>
                      </div>
                    )}
                  </article>
                </div>
              ) : (
                renderQuizPanel()
              )}
            </div>
          </div>
        </div>
      )}

      {lesson && slide && slideMode && (
        <div className="lesson-view">
          <Crumbs
            parts={[
              { label: "Subjects", to: "/" },
              { label: subjectName, to: subjectPath },
              { label: subtopicTitle },
            ]}
          />
          <div className="back-row">
            <PushButton variant="soft" size="sm" onClick={() => setSlideMode(false)}>
              ← Back to lesson overview
            </PushButton>
          </div>

          <div className="lesson-layout">
            <div className="lesson-layout__main">
              {renderTabs()}

              {topTab === "lesson" ? (
                <div
                  className="lesson-tab-panel"
                  role="tabpanel"
                  id="lesson-tab-panel"
                  aria-labelledby="lesson-tab"
                >
                  <article className="panel reading">
                    <div className="reading__header">
                      <h2>{slide.title}</h2>
                    </div>
                    <div className="reading__body markdown">
                      <MarkdownContent>{slide.content}</MarkdownContent>
                    </div>
                    <div className="reading__footer slide-nav">
                      <div className="slide-nav__controls">
                        <PushButton
                          variant="outline"
                          size="sm"
                          disabled={slideIndex === 0}
                          onClick={() => {
                            const prev = Math.max(0, slideIndex - 1);
                            setSlideIndex(prev);
                            void persistSlidePosition(prev);
                          }}
                        >
                          Previous
                        </PushButton>
                        <PushButton size="sm" disabled={atEnd} onClick={() => void goNext()}>
                          Next slide
                        </PushButton>
                      </div>
                      <p className="slide-nav__status">
                        Slide {slideIndex + 1} of {slides.length}
                        {lessonComplete ? " · complete" : ""}
                      </p>
                    </div>
                  </article>
                </div>
              ) : (
                renderQuizPanel()
              )}
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Link, useParams } from "react-router-dom";

import { getLesson } from "../api/materials";
import type { LessonMaterial } from "../api/types";
import { ApiError } from "../api/types";
import { AppShell } from "../components/AppShell";
import { PushButton } from "../components/PushButton";

type ViewMode = "slides" | "full";

export function LessonPage() {
  const { topicId = "" } = useParams();
  const [lesson, setLesson] = useState<LessonMaterial | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<ViewMode>("slides");
  const [slideIndex, setSlideIndex] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLesson(null);
    setError(null);
    setSlideIndex(0);
    void (async () => {
      try {
        const data = await getLesson(topicId);
        if (!cancelled) {
          setLesson(data);
          if (!data.slides.length) {
            setMode("full");
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
  }, [topicId]);

  const slides = lesson?.slides ?? [];
  const slide = slides[slideIndex];

  return (
    <AppShell>
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
          <Link to="/">
            <PushButton variant="soft">Back to topics</PushButton>
          </Link>
        </div>
      )}

      {lesson && (
        <div className="lesson-layout">
          <header className="page-head">
            <div>
              <p className="muted" style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)" }}>
                2.0 Study
              </p>
              <h1 className="page-head__title">{lesson.title}</h1>
            </div>
          </header>

          <div className="lesson-nav">
            {slides.length > 0 && (
              <div className="tabs" role="tablist" aria-label="Lesson view">
                <button
                  type="button"
                  className={`tabs__btn ${mode === "slides" ? "is-active" : ""}`}
                  onClick={() => setMode("slides")}
                >
                  Slides
                </button>
                <button
                  type="button"
                  className={`tabs__btn ${mode === "full" ? "is-active" : ""}`}
                  onClick={() => setMode("full")}
                >
                  Full lesson
                </button>
              </div>
            )}
            <Link to={`/topics/${topicId}/quiz`}>
              <PushButton color="cyan">
                Start the quiz <span className="btn__arrow">→</span>
              </PushButton>
            </Link>
          </div>

          {mode === "slides" && slide && (
            <article className="slide-panel">
              <p className="slide-panel__kicker">
                Slide {slide.number} of {slides.length}
              </p>
              <h2 style={{ fontSize: "var(--text-2xl)", marginBottom: "var(--space-md)" }}>
                {slide.title}
              </h2>
              <div className="markdown">
                <ReactMarkdown>{slide.content}</ReactMarkdown>
              </div>
              <div className="form__actions" style={{ marginTop: "var(--space-xl)" }}>
                <PushButton
                  variant="outline"
                  disabled={slideIndex === 0}
                  onClick={() => setSlideIndex((i) => Math.max(0, i - 1))}
                >
                  Previous
                </PushButton>
                {slideIndex < slides.length - 1 ? (
                  <PushButton
                    color="pear"
                    onClick={() => setSlideIndex((i) => Math.min(slides.length - 1, i + 1))}
                  >
                    Next slide <span className="btn__arrow">→</span>
                  </PushButton>
                ) : (
                  <Link to={`/topics/${topicId}/quiz`}>
                    <PushButton color="coral">
                      Ready for quiz <span className="btn__arrow">→</span>
                    </PushButton>
                  </Link>
                )}
              </div>
            </article>
          )}

          {mode === "full" && (
            <article className="slide-panel">
              <div className="markdown">
                <ReactMarkdown>{lesson.markdown}</ReactMarkdown>
              </div>
              <div className="form__actions" style={{ marginTop: "var(--space-xl)" }}>
                <Link to={`/topics/${topicId}/quiz`}>
                  <PushButton color="coral">
                    Start the quiz <span className="btn__arrow">→</span>
                  </PushButton>
                </Link>
              </div>
            </article>
          )}
        </div>
      )}
    </AppShell>
  );
}

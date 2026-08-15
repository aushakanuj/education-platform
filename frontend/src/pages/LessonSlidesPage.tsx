import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { updateMaterialProgress } from "../api/materials";
import { ApiError } from "../api/types";
import { AppShell } from "../components/AppShell";
import { Crumbs } from "../components/Crumbs";
import { MarkdownContent } from "../components/MarkdownContent";
import { PushButton } from "../components/PushButton";
import { resumeSlideIndex, useSubtopicLesson } from "../lib/useSubtopicLesson";

export function LessonSlidesPage() {
  const {
    lesson,
    setLesson,
    subjectName,
    subtopicTitle,
    error,
    setError,
    slides,
    subjectPath,
    lessonPath,
    subtopicId,
  } = useSubtopicLesson();
  const [searchParams] = useSearchParams();
  const [slideIndex, setSlideIndex] = useState(0);
  const startedRef = useRef(false);

  useEffect(() => {
    startedRef.current = false;
    setSlideIndex(0);
  }, [subtopicId]);

  useEffect(() => {
    if (!lesson || startedRef.current) return;
    startedRef.current = true;
    const fromStart = searchParams.get("from") === "start";
    setSlideIndex(fromStart ? 0 : resumeSlideIndex(lesson, lesson.slides));
  }, [lesson, searchParams]);

  const slide = slides[slideIndex];
  const atEnd = slides.length > 0 && slideIndex === slides.length - 1;
  const lessonComplete = Boolean(lesson?.progress?.status === "completed");

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
          <Link to={lessonPath}>
            <PushButton variant="matte">Back to lesson</PushButton>
          </Link>
        </div>
      )}

      {lesson && slide && (
        <div className="lesson-view">
          <Crumbs
            parts={[
              { label: "Subjects", to: "/" },
              { label: subjectName, to: subjectPath },
              { label: subtopicTitle, to: lessonPath },
              { label: "Slides" },
            ]}
          />
          <div className="back-row">
            <Link to={lessonPath} className="btn btn--matte btn--sm">
              ← Back to lesson overview
            </Link>
          </div>

          <div className="lesson-slides">
            <article className="panel lesson-overview">
              <div className="lesson-overview__header">
                <h2>{slide.title}</h2>
              </div>
              <div className="lesson-overview__scroll markdown">
                <MarkdownContent>{slide.content}</MarkdownContent>
              </div>
              <div className="lesson-overview__footer">
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
        </div>
      )}
    </AppShell>
  );
}

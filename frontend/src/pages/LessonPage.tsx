import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { fetchLearningDirectory, getSubtopicMaterial, updateMaterialProgress } from "../api/materials";
import type { LessonMaterial } from "../api/types";
import { ApiError } from "../api/types";
import { AppShell } from "../components/AppShell";
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
  const [error, setError] = useState<string | null>(null);
  const [slideIndex, setSlideIndex] = useState(0);
  const openedRef = useRef(false);

  const topicPath = `/subjects/${subjectId}/topics/${topicId}`;

  useEffect(() => {
    let cancelled = false;
    openedRef.current = false;
    setLesson(null);
    setError(null);
    setSlideIndex(0);
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
        <>
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
              Subtopic lesson · slide {slideIndex + 1} of {slides.length}
            </p>
            <h1>{subtopicTitle}</h1>
            <p>
              Finish every slide to unlock the subtopic quiz. Subtopic completion reaches 100%
              after you pass the quiz.
            </p>
          </header>

          <div className="progress-label">
            Lesson slides · {progressPct}%
            {lessonComplete ? " · lesson complete" : ""}
          </div>
          <div className="progress" aria-hidden="true" style={{ marginBottom: "0.75rem" }}>
            <span style={{ width: `${progressPct}%` }} />
          </div>
          <div className="progress-label">Subtopic completion · {Math.round(subtopicPct)}%</div>
          <div className="progress" aria-hidden="true" style={{ marginBottom: "1rem" }}>
            <span style={{ width: `${subtopicPct}%` }} />
          </div>

          <article className="panel reading">
            <h2>{slide.title}</h2>
            <div className="markdown">
              <MarkdownContent>{slide.content}</MarkdownContent>
            </div>
            <div className="slide-nav">
              <PushButton
                variant="outline"
                disabled={slideIndex === 0}
                onClick={() => setSlideIndex((i) => Math.max(0, i - 1))}
              >
                Previous
              </PushButton>
              <div className="actions" style={{ margin: 0 }}>
                <Link to={topicPath} className="btn btn--soft">
                  Back to topic
                </Link>
                <PushButton disabled={atEnd} onClick={() => void goNext()}>
                  Next slide
                </PushButton>
                {quizUnlocked && lesson.quiz_id ? (
                  <Link to={`/quizzes/${lesson.quiz_id}`} className="btn">
                    Start subtopic quiz
                  </Link>
                ) : (
                  <button type="button" className="btn" disabled>
                    Start subtopic quiz
                  </button>
                )}
              </div>
            </div>
            {!quizUnlocked && (
              <p className="alert alert--warning" style={{ marginTop: "1rem", marginBottom: 0 }}>
                Reach the final slide to unlock the quiz.
              </p>
            )}
          </article>
        </>
      )}
    </AppShell>
  );
}

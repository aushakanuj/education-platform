import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { listTopics } from "../api/materials";
import type { TopicSummary } from "../api/types";
import { ApiError } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { AppShell } from "../components/AppShell";
import { StudyBuddy } from "../components/StudyBuddy";

export function HomePage() {
  const { enrollments } = useAuth();
  const [topics, setTopics] = useState<TopicSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const subject = enrollments?.subject_enrollments.find((s) => s.status === "active");
  const grade = enrollments?.grade_enrollments.find((g) => g.status === "active");

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await listTopics();
        if (!cancelled) {
          setTopics(data);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Could not load topics.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <AppShell>
      <header className="page-head">
        <div>
          <h1 className="page-head__title">Your study path</h1>
          <p className="page-head__lede">
            {grade?.grade_name ?? "Grade"} · {subject?.subject_name ?? "Subject"}. Pick a topic,
            read the lesson, then take the quiz.
          </p>
        </div>
        <StudyBuddy size="lg" />
      </header>

      <section className="workflow" aria-label="How it works">
        <article className="workflow__stage" style={{ ["--stage-accent" as string]: "var(--color-accent)" }}>
          <div className="workflow__num">1.0</div>
          <div>
            <h2 className="workflow__title">Enroll</h2>
            <p className="workflow__body">You’re in. Curriculum unlocked for this subject.</p>
          </div>
        </article>
        <article
          className="workflow__stage"
          style={{ ["--stage-accent" as string]: "var(--color-accent-2)" }}
        >
          <div className="workflow__num">2.0</div>
          <div>
            <h2 className="workflow__title">Study</h2>
            <p className="workflow__body">Open a topic and work through the lesson slides.</p>
          </div>
        </article>
        <article
          className="workflow__stage"
          style={{ ["--stage-accent" as string]: "var(--color-lavender)" }}
        >
          <div className="workflow__num">3.0</div>
          <div>
            <h2 className="workflow__title">Quiz</h2>
            <p className="workflow__body">Answer every question, then submit for a score.</p>
          </div>
        </article>
        <article
          className="workflow__stage"
          style={{ ["--stage-accent" as string]: "var(--color-accent-3)" }}
        >
          <div className="workflow__num">4.0</div>
          <div>
            <h2 className="workflow__title">Result</h2>
            <p className="workflow__body">See what you got right. Pass mark is 70%.</p>
          </div>
        </article>
      </section>

      <h2 style={{ fontSize: "var(--text-2xl)", marginBottom: "var(--space-lg)" }}>Topics</h2>

      {error && (
        <p className="form__error" role="alert">
          {error}
        </p>
      )}

      {!topics && !error && (
        <p className="muted" role="status">
          Loading topics…
        </p>
      )}

      {topics && topics.length === 0 && (
        <div className="banner--info">
          <p>No published topics yet. Ask your teacher to seed the curriculum.</p>
        </div>
      )}

      {topics && topics.length > 0 && (
        <div className="topic-grid">
          {topics.map((topic) => (
            <Link key={topic.id} to={`/topics/${topic.id}`} className="topic-card">
              <h3 className="topic-card__title">{topic.title}</h3>
              <div className="topic-card__meta">
                {topic.has_lesson && <span className="chip">Lesson</span>}
                {topic.has_quiz && <span className="chip">Quiz</span>}
              </div>
            </Link>
          ))}
        </div>
      )}
    </AppShell>
  );
}

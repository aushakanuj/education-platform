import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { fetchLearningDirectory } from "../api/materials";
import type { LearningDirectory, SubjectNode } from "../api/types";
import { ApiError } from "../api/types";
import { AppShell } from "../components/AppShell";
import { Crumbs } from "../components/Crumbs";

const PLACEHOLDER_SUBJECTS = [
  {
    key: "science",
    name: "Science",
    blurb: "Living world, matter, and energy for Grade 8.",
    locked: true,
  },
  {
    key: "english",
    name: "English",
    blurb: "Reading comprehension and writing craft.",
    locked: true,
  },
  {
    key: "social",
    name: "Social Studies",
    blurb: "Civics, geography, and local history.",
    locked: true,
  },
] as const;

const SUBJECT_BLURBS: Record<string, string> = {
  Mathematics: "Number sense, algebra foundations, and geometry basics.",
  MATH: "Number sense, algebra foundations, and geometry basics.",
};

function topicsComplete(subject: SubjectNode): { done: number; total: number; pct: number } {
  const total = subject.topics.length;
  const done = subject.topics.filter((topic) => topic.complete).length;
  return {
    done,
    total,
    pct: total === 0 ? 0 : Math.round(subject.progress_percent),
  };
}

function subjectBlurb(subject: SubjectNode): string {
  return (
    SUBJECT_BLURBS[subject.name] ??
    SUBJECT_BLURBS[subject.code] ??
    `${subject.grade_name} · ${subject.academic_period_name}`
  );
}

export function HomePage() {
  const { subjectId } = useParams();
  const [directory, setDirectory] = useState<LearningDirectory | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await fetchLearningDirectory();
        if (!cancelled) setDirectory(data);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Could not load subjects.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const subjects = directory?.subjects ?? [];
  const selected = useMemo(() => {
    if (!subjectId) return null;
    return subjects.find((item) => item.id === subjectId) ?? null;
  }, [subjects, subjectId]);

  const knownNames = new Set(subjects.map((s) => s.name.toLowerCase()));
  const placeholders = PLACEHOLDER_SUBJECTS.filter((p) => !knownNames.has(p.name.toLowerCase()));

  if (selected) {
    return (
      <AppShell>
        <Crumbs
          parts={[
            { label: "Subjects", to: "/" },
            { label: selected.name },
          ]}
        />
        <div className="back-row">
          <Link to="/" className="btn btn--outline btn--sm">
            ← Back to subjects
          </Link>
        </div>
        <header className="page-head">
          <p className="kicker">Subject overview</p>
          <h1>{selected.name}</h1>
          <p>{subjectBlurb(selected)}</p>
        </header>

        {selected.topics.length === 0 ? (
          <div className="alert alert--info">No topics published yet.</div>
        ) : (
          <div className="grid grid--2">
            {selected.topics.map((topic) => {
              const done = topic.subtopics.filter((s) => s.progress_percent === 100).length;
              return (
                <Link
                  key={topic.id}
                  to={`/subjects/${selected.id}/topics/${topic.id}`}
                  className="card"
                >
                  <h3>{topic.title}</h3>
                  <p>
                    {topic.subtopics.length} subtopics · overall quiz{" "}
                    {topic.overall_quiz?.unlocked ? "unlocked" : "locked"}
                  </p>
                  <div className="progress-label">
                    {done}/{topic.subtopics.length} subtopics complete · topic{" "}
                    {Math.round(topic.progress_percent)}%
                  </div>
                  <div className="progress" aria-hidden="true">
                    <span style={{ width: `${topic.progress_percent}%` }} />
                  </div>
                  <div className="meta-row">
                    {topic.complete ? (
                      <span className="badge badge--ok">Topic complete</span>
                    ) : (
                      <span className="badge badge--info">In progress</span>
                    )}
                    {topic.overall_quiz?.passed && (
                      <span className="badge badge--ok">Overall quiz passed</span>
                    )}
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </AppShell>
    );
  }

  return (
    <AppShell>
      <Crumbs parts={[{ label: "Subjects" }]} />
      <header className="page-head">
        <p className="kicker">Student dashboard · demo data</p>
        <h1>Your subjects</h1>
        <p>
          Pick a subject to browse topics and subtopics. Track lesson and quiz progress, review
          attempt history, and unlock the overall topic quiz after every subtopic quiz is passed.
        </p>
      </header>

      {error && (
        <p className="form__error" role="alert">
          {error}
        </p>
      )}

      {!directory && !error && (
        <p className="muted" role="status">
          Loading subjects…
        </p>
      )}

      {directory && subjects.length === 0 && placeholders.length === 0 && (
        <div className="alert alert--info">
          No enrolled subjects with published curriculum yet.
        </div>
      )}

      {(subjects.length > 0 || placeholders.length > 0) && (
        <div className="grid grid--2">
          {subjects.map((subject) => {
            const prog = topicsComplete(subject);
            const empty = subject.topics.length === 0;
            if (empty) {
              return (
                <div key={subject.id} className="card is-locked">
                  <h2>{subject.name}</h2>
                  <p>{subjectBlurb(subject)}</p>
                  <div className="progress-label">Coming soon</div>
                  <div className="meta-row">
                    <span className="badge badge--locked">Locked</span>
                  </div>
                </div>
              );
            }
            return (
              <Link key={subject.id} to={`/subjects/${subject.id}`} className="card">
                <h2>{subject.name}</h2>
                <p>{subjectBlurb(subject)}</p>
                <div className="progress-label">
                  {prog.done}/{prog.total} topics complete · {prog.pct}%
                </div>
                <div className="progress" aria-hidden="true">
                  <span style={{ width: `${prog.pct}%` }} />
                </div>
                <div className="meta-row">
                  <span className="badge badge--info">{subject.topics.length} topics</span>
                </div>
              </Link>
            );
          })}
          {placeholders.map((item) => (
            <div key={item.key} className="card is-locked" aria-disabled="true">
              <h2>{item.name}</h2>
              <p>{item.blurb}</p>
              <div className="progress-label">Coming soon</div>
              <div className="meta-row">
                <span className="badge badge--locked">Locked</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </AppShell>
  );
}

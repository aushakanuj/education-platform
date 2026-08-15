import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { fetchLearningDirectory } from "../api/materials";
import type { LearningDirectory, SubjectNode, TopicNode } from "../api/types";
import { ApiError } from "../api/types";
import { AppShell } from "../components/AppShell";
import { Crumbs } from "../components/Crumbs";
import { SchoolMaterialPanel } from "../components/SchoolMaterialPanel";
import { BACKDROP_CHROME_ANCHOR, setBackdropChrome } from "../lib/backdropChrome";
import { schoolTopic, subjectProgress } from "../lib/subjectMaterial";

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

function subjectBlurb(subject: SubjectNode): string {
  return (
    SUBJECT_BLURBS[subject.name] ??
    SUBJECT_BLURBS[subject.code] ??
    `${subject.grade_name} · ${subject.academic_period_name}`
  );
}

function SubjectMaterialView({
  subjectId,
  subjectName,
  curriculum,
}: {
  subjectId: string;
  subjectName: string;
  curriculum: TopicNode | null;
}) {
  useEffect(() => {
    if (!curriculum) {
      setBackdropChrome(null);
      return;
    }

    const done = curriculum.subtopics.filter((s) => s.progress_percent === 100).length;
    const total = curriculum.subtopics.length;
    setBackdropChrome({
      progressPercent: curriculum.progress_percent,
      progressLabel: `Subject completion · ${Math.round(curriculum.progress_percent)}% · ${done}/${total} units · overall quiz ${
        curriculum.overall_quiz?.passed ? "passed" : "pending"
      }`,
      statusLabel: curriculum.complete ? "Complete" : "In progress",
      complete: curriculum.complete,
    });

    return () => setBackdropChrome(null);
  }, [curriculum]);

  const progressSr =
    curriculum &&
    `Subject completion · ${Math.round(curriculum.progress_percent)}% · ${
      curriculum.subtopics.filter((s) => s.progress_percent === 100).length
    }/${curriculum.subtopics.length} units · overall quiz ${
      curriculum.overall_quiz?.passed ? "passed" : "pending"
    }`;

  return (
    <AppShell subjectTitle={subjectName}>
      <div className="subject-view">
        <header className="subject-view__head">
          <Crumbs
            parts={[
              { label: "Subjects", to: "/" },
              { label: subjectName },
            ]}
          />
          <div className="subject-view__toolbar">
            <Link to="/" className="btn btn--matte btn--sm subject-view__back">
              ← Back to subjects
            </Link>
          </div>
          <div className="subject-view__chrome-slot" {...{ [BACKDROP_CHROME_ANCHOR]: "" }}>
            <h1 id="school-material-heading" className="sr-only">
              School material
            </h1>
            {progressSr && <p className="sr-only">{progressSr}</p>}
          </div>
        </header>

        <section className="material-pane material-pane--school" aria-labelledby="school-material-heading">
          {!curriculum ? (
            <div className="alert alert--info">No school material published yet.</div>
          ) : (
            <SchoolMaterialPanel subjectId={subjectId} subjectName={subjectName} topic={curriculum} />
          )}
        </section>
      </div>
    </AppShell>
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
      <SubjectMaterialView
        subjectId={selected.id}
        subjectName={selected.name}
        curriculum={schoolTopic(selected)}
      />
    );
  }

  return (
    <AppShell>
      <Crumbs parts={[{ label: "Subjects" }]} />
      <header className="page-head">
        <h1 className="sr-only">Your subjects</h1>
        <p>
          Pick a subject to open school material, track lesson and quiz progress, and review attempt
          history.
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
            const prog = subjectProgress(subject);
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
                  {prog.done}/{prog.total} units complete · {prog.pct}%
                </div>
                <div
                  className={`progress ${prog.pct >= 100 ? "progress--complete" : "progress--in-progress"}`}
                  aria-hidden="true"
                >
                  <span style={{ width: `${prog.pct}%` }} />
                </div>
                <div className="meta-row">
                  <span className="badge badge--info">School material</span>
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

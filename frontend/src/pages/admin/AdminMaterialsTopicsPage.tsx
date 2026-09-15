import { useEffect, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";

import { isInFlightGenerationPhase, listTopicGenerationRuns, submitSubjectGenerationRun } from "../../api/generation";
import { ApiError } from "../../api/types";
import { Crumbs } from "../../components/Crumbs";
import { PushButton } from "../../components/PushButton";
import {
  adminTopicPath,
  subjectTopicLessonTopics,
  subjectUnitCards,
  type AdminTopic,
  type AdminUnitCard,
} from "../../lib/adminCurriculumLive";
import { useAdminDirectory } from "../../lib/useAdminDirectory";

type TopicListBadge = "published" | "in_flight" | "unpublished";

function topicListBadge(published: boolean, inFlight: boolean): TopicListBadge {
  if (inFlight) return "in_flight";
  if (published) return "published";
  return "unpublished";
}

function TopicStatusBadge({ badge }: { badge: TopicListBadge }) {
  switch (badge) {
    case "published":
      return <span className="badge badge--ok">published</span>;
    case "in_flight":
      return <span className="badge">in progress</span>;
    case "unpublished":
      return null;
    default: {
      const _never: never = badge;
      return _never;
    }
  }
}

function unitHref(gradeKey: string, subjectId: string, card: AdminUnitCard): string {
  if (card.hasLesson) {
    return adminTopicPath(gradeKey, subjectId, card.topicId, {
      published: true,
      unitId: card.unitId,
    });
  }
  return adminTopicPath(gradeKey, subjectId, card.topicId);
}

function AdminUnitCardRow({
  gradeKey,
  subjectId,
  card,
  index,
  inFlight,
}: {
  gradeKey: string;
  subjectId: string;
  card: AdminUnitCard;
  index: number;
  inFlight: boolean;
}) {
  return (
    <li className="subtopic-card">
      <Link to={unitHref(gradeKey, subjectId, card)} className="subtopic-card__head">
        <div className="list-item__num">{String(index + 1).padStart(2, "0")}</div>
        <div>
          <p className="list-item__title">{card.title}</p>
          {card.quizTitle ? <p className="list-item__meta">{card.quizTitle}</p> : null}
        </div>
        <div className="subtopic-card__quiz-col">
          <TopicStatusBadge badge={topicListBadge(card.hasLesson, inFlight)} />
        </div>
        <span className="subtopic-card__chevron" aria-hidden="true">
          ›
        </span>
      </Link>
    </li>
  );
}

function AdminTopicLessonCard({
  gradeKey,
  subjectId,
  topic,
  inFlight,
}: {
  gradeKey: string;
  subjectId: string;
  topic: AdminTopic;
  inFlight: boolean;
}) {
  return (
    <section
      className="school-section school-section--topic-lesson"
      aria-labelledby={`topic-lesson-heading-${topic.id}`}
    >
      <header className="school-section__head">
        <div>
          <p className="school-section__eyebrow">Topic lesson</p>
          <h2 id={`topic-lesson-heading-${topic.id}`}>{topic.title}</h2>
          <p>Published lesson and quiz for this subject.</p>
        </div>
        <TopicStatusBadge badge={topicListBadge(topic.hasTopicLesson, inFlight)} />
      </header>
      <p className="topic-lesson-card__copy">
        Open the published slides and independently scrolling quiz.
      </p>
      <div className="topic-lesson-card__actions">
        <Link
          to={adminTopicPath(gradeKey, subjectId, topic.id, { published: true })}
          className="btn btn--sm"
        >
          Open topic lesson
        </Link>
      </div>
    </section>
  );
}

export function AdminMaterialsTopicsPage() {
  const { gradeKey = "", subjectId = "" } = useParams();
  const navigate = useNavigate();
  const { grades, loading, error, getSubject } = useAdminDirectory();
  const found = getSubject(gradeKey, subjectId);
  const [showUpload, setShowUpload] = useState(false);
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [inFlightByTopic, setInFlightByTopic] = useState<Record<string, boolean>>({});

  const grade = found?.grade;
  const subject = found?.subject;
  const unitCards = subject ? subjectUnitCards(subject) : [];
  const topicLessons = subject ? subjectTopicLessonTopics(subject) : [];

  useEffect(() => {
    if (!subject) return;
    let cancelled = false;
    void (async () => {
      const entries = await Promise.all(
        subject.topics.map(async (topic) => {
          try {
            const runs = await listTopicGenerationRuns(topic.id);
            return [topic.id, runs.some((run) => isInFlightGenerationPhase(run.phase))] as const;
          } catch {
            return [topic.id, false] as const;
          }
        }),
      );
      if (!cancelled) setInFlightByTopic(Object.fromEntries(entries));
    })();
    return () => {
      cancelled = true;
    };
  }, [subject]);

  if (!loading && !error && grades && !found) {
    return <Navigate to="/admin/materials" replace />;
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!subject || !grade || !file || busy) return;
    const resolvedTitle = title.trim() || file.name.replace(/\.pdf$/i, "");
    setBusy(true);
    setUploadError(null);
    try {
      const accepted = await submitSubjectGenerationRun(subject.id, file, resolvedTitle);
      navigate(
        `/admin/materials/grades/${grade.key}/subjects/${subject.id}/topics/${accepted.topic_id}`,
      );
    } catch (err) {
      setUploadError(err instanceof ApiError ? err.message : "Upload failed. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="admin-materials">
      <Crumbs
        parts={[
          { label: "Materials", to: "/admin/materials" },
          {
            label: grade?.name ?? "Grade",
            to: grade ? `/admin/materials/grades/${grade.key}` : undefined,
          },
          { label: subject?.name ?? "Subject" },
        ]}
      />
      <header className="page-head page-head--with-actions">
        <div>
          <p className="kicker">
            {grade?.name ?? "…"} · {subject?.name ?? "…"}
          </p>
          <h1>Topics</h1>
          <p>Open a unit to review the published lesson and quiz, or upload a PDF to add a unit.</p>
        </div>
        <div className="page-head__actions">
          <button
            type="button"
            className="btn btn--outline"
            aria-expanded={showUpload}
            aria-controls="topic-upload-panel"
            onClick={() => setShowUpload((open) => !open)}
          >
            Upload
          </button>
        </div>
      </header>

      {showUpload && subject && (
        <section
          id="topic-upload-panel"
          className="panel admin-materials__upload"
          aria-label="Upload topic PDF"
        >
          <form onSubmit={(event) => void onSubmit(event)}>
            <div className="form__field">
              <label className="form__label" htmlFor="subject-topic-title">
                Title
              </label>
              <input
                id="subject-topic-title"
                className="form__input"
                type="text"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="Topic title"
                disabled={busy}
              />
            </div>
            <div className="form__field">
              <label className="form__label" htmlFor="subject-topic-file">
                PDF file
              </label>
              <input
                id="subject-topic-file"
                className="form__input"
                type="file"
                accept="application/pdf,.pdf"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                disabled={busy}
              />
            </div>
            {uploadError ? (
              <p className="form__error" role="alert">
                {uploadError}
              </p>
            ) : null}
            <div className="admin-upload__actions">
              <PushButton type="submit" disabled={!file || busy} loading={busy}>
                {busy ? "Uploading…" : "Upload topic PDF"}
              </PushButton>
            </div>
          </form>
        </section>
      )}

      {loading && (
        <p className="muted" role="status">
          Loading curriculum…
        </p>
      )}
      {error && (
        <p className="form__error" role="alert">
          {error}
        </p>
      )}
      {subject && grade && (
        <div className="school-material-stack">
          {topicLessons.map((topic) => (
            <AdminTopicLessonCard
              key={topic.id}
              gradeKey={grade.key}
              subjectId={subject.id}
              topic={topic}
              inFlight={Boolean(inFlightByTopic[topic.id])}
            />
          ))}
          <section className="school-section school-section--units" aria-labelledby="units-heading">
            <header className="school-section__head">
              <h2 id="units-heading">Units</h2>
              <p>Review each unit lesson and quiz.</p>
            </header>
            {unitCards.length === 0 ? (
              <p className="muted">No units published for this subject yet.</p>
            ) : (
              <ul className="list">
                {unitCards.map((card, index) => (
                  <AdminUnitCardRow
                    key={card.key}
                    gradeKey={grade.key}
                    subjectId={subject.id}
                    card={card}
                    index={index}
                    inFlight={Boolean(inFlightByTopic[card.topicId])}
                  />
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

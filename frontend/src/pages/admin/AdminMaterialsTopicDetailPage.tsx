import { useMemo, useState } from "react";
import { Navigate, useParams } from "react-router-dom";

import { Crumbs } from "../../components/Crumbs";
import { CurriculumMaterialUpload } from "../../components/CurriculumMaterialUpload";
import type { PublishStatus } from "../../lib/adminCurriculumLive";
import { useAdminDirectory } from "../../lib/useAdminDirectory";

type TabId = "lessons" | "quizzes";

function StatusBadge({ status }: { status: PublishStatus }) {
  return <span className="badge badge--ok">{status}</span>;
}

export function AdminMaterialsTopicDetailPage() {
  const { gradeKey = "", subjectId = "", topicId = "" } = useParams();
  const { grades, loading, error, getTopic } = useAdminDirectory();
  const found = getTopic(gradeKey, subjectId, topicId);
  const [tab, setTab] = useState<TabId>("lessons");
  const [uploadSubtopicId, setUploadSubtopicId] = useState<string | null>(null);

  const quizRows = useMemo(() => {
    if (!found) return [];
    const { topic } = found;
    const rows: {
      id: string;
      title: string;
      meta: string;
      status: PublishStatus;
    }[] = [];
    for (const st of topic.subtopics) {
      if (st.quiz) {
        rows.push({
          id: st.quiz.id,
          title: st.quiz.title,
          meta: `Subtopic check · ${st.title}`,
          status: st.quiz.status,
        });
      }
    }
    if (topic.masteryQuiz) {
      rows.push({
        id: topic.masteryQuiz.id,
        title: topic.masteryQuiz.title,
        meta: "Topic mastery",
        status: topic.masteryQuiz.status,
      });
    }
    return rows;
  }, [found]);

  if (!loading && !error && grades && !found) {
    return <Navigate to="/admin/materials" replace />;
  }

  const grade = found?.grade;
  const subject = found?.subject;
  const topic = found?.topic;
  const activeUpload = topic?.subtopics.find((st) => st.id === uploadSubtopicId) ?? null;

  return (
    <div className="admin-materials">
      <Crumbs
        parts={[
          { label: "Materials", to: "/admin/materials" },
          {
            label: grade?.name ?? "Grade",
            to: grade ? `/admin/materials/grades/${grade.key}` : undefined,
          },
          {
            label: subject?.name ?? "Subject",
            to:
              grade && subject
                ? `/admin/materials/grades/${grade.key}/subjects/${subject.id}`
                : undefined,
          },
          { label: topic?.unitLabel ?? "Unit" },
        ]}
      />
      <header className="page-head page-head--with-actions">
        <div>
          <p className="kicker">
            {subject?.name ?? "…"} · {topic?.unitLabel ?? "…"}
          </p>
          <h1>{topic?.title ?? "Unit"}</h1>
          <p>Browse lessons and quizzes. Upload a PDF under a subtopic to enqueue ingest.</p>
        </div>
        {topic && <StatusBadge status={topic.status} />}
      </header>

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

      {topic && (
        <>
          <div className="admin-tabs" role="tablist" aria-label="Unit content">
            <button
              type="button"
              role="tab"
              id="tab-lessons"
              aria-selected={tab === "lessons"}
              aria-controls="panel-lessons"
              className={`admin-tabs__tab ${tab === "lessons" ? "is-active" : ""}`}
              onClick={() => setTab("lessons")}
            >
              Lessons
            </button>
            <button
              type="button"
              role="tab"
              id="tab-quizzes"
              aria-selected={tab === "quizzes"}
              aria-controls="panel-quizzes"
              className={`admin-tabs__tab ${tab === "quizzes" ? "is-active" : ""}`}
              onClick={() => setTab("quizzes")}
            >
              Quizzes
            </button>
          </div>

          {tab === "lessons" ? (
            <div
              className="panel"
              role="tabpanel"
              id="panel-lessons"
              aria-labelledby="tab-lessons"
            >
              <ul className="list">
                {topic.subtopics.map((st) => (
                  <li key={st.id} className="list-item list-item--with-actions">
                    <span className="list-item__num">{st.order}</span>
                    <div>
                      <p className="list-item__title">{st.title}</p>
                      <p className="list-item__meta">
                        {st.lesson ? st.lesson.title : "No lesson yet"}
                      </p>
                    </div>
                    <div className="list-item__actions">
                      {st.lesson ? (
                        <StatusBadge status={st.lesson.status} />
                      ) : (
                        <span className="badge badge--locked">missing</span>
                      )}
                      <button
                        type="button"
                        className="btn btn--outline btn--sm"
                        aria-expanded={uploadSubtopicId === st.id}
                        onClick={() =>
                          setUploadSubtopicId((cur) => (cur === st.id ? null : st.id))
                        }
                      >
                        Upload
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
              {activeUpload && (
                <div className="admin-materials__upload admin-materials__upload--nested">
                  <p className="admin-upload__target muted">
                    Upload PDF for <strong>{activeUpload.title}</strong>
                  </p>
                  <CurriculumMaterialUpload
                    key={activeUpload.id}
                    subtopicId={activeUpload.id}
                    defaultTitle={activeUpload.title}
                    compact
                  />
                </div>
              )}
            </div>
          ) : (
            <div
              className="panel"
              role="tabpanel"
              id="panel-quizzes"
              aria-labelledby="tab-quizzes"
            >
              {quizRows.length === 0 ? (
                <p className="muted">No quizzes in this unit.</p>
              ) : (
                <ul className="list">
                  {quizRows.map((row, index) => (
                    <li key={row.id} className="list-item">
                      <span className="list-item__num">{index + 1}</span>
                      <div>
                        <p className="list-item__title">{row.title}</p>
                        <p className="list-item__meta">{row.meta}</p>
                      </div>
                      <StatusBadge status={row.status} />
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

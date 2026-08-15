import { Link, Navigate, useParams } from "react-router-dom";

import { Crumbs } from "../../components/Crumbs";
import { useAdminDirectory } from "../../lib/useAdminDirectory";

export function AdminMaterialsTopicsPage() {
  const { gradeKey = "", subjectId = "" } = useParams();
  const { grades, loading, error, getSubject } = useAdminDirectory();
  const found = getSubject(gradeKey, subjectId);

  if (!loading && !error && grades && !found) {
    return <Navigate to="/admin/materials" replace />;
  }

  const grade = found?.grade;
  const subject = found?.subject;

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
      <div className="back-row">
        <Link
          to={grade ? `/admin/materials/grades/${grade.key}` : "/admin/materials"}
          className="btn btn--matte btn--sm"
        >
          ← Back to subjects
        </Link>
      </div>
      <header className="page-head">
        <p className="kicker">
          {grade?.name ?? "…"} · {subject?.name ?? "…"}
        </p>
        <h1>Units</h1>
        <p>
          Topics are shown as units in the student product. Open a unit to review lessons and quizzes.
        </p>
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
      {subject && grade && (
        <ul className="list">
          {subject.topics.map((topic) => (
            <li key={topic.id}>
              <Link
                to={`/admin/materials/grades/${grade.key}/subjects/${subject.id}/topics/${topic.id}`}
                className="list-item admin-topic-row"
              >
                <span className="list-item__num">{topic.order}</span>
                <div>
                  <p className="list-item__title">
                    {topic.unitLabel}: {topic.title}
                  </p>
                  <p className="list-item__meta">
                    {topic.subtopics.length} subtopics
                    {topic.masteryQuiz ? " · mastery quiz" : ""}
                  </p>
                </div>
                <span className="badge badge--ok">{topic.status}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

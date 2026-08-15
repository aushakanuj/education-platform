import { Link, Navigate, useParams } from "react-router-dom";

import { Crumbs } from "../../components/Crumbs";
import { countTopics } from "../../lib/adminCurriculumLive";
import { useAdminDirectory } from "../../lib/useAdminDirectory";

export function AdminMaterialsSubjectsPage() {
  const { gradeKey = "" } = useParams();
  const { grades, loading, error, getGrade } = useAdminDirectory();
  const grade = getGrade(gradeKey);

  if (!loading && !error && grades && !grade) {
    return <Navigate to="/admin/materials" replace />;
  }

  return (
    <div className="admin-materials">
      <Crumbs
        parts={[
          { label: "Materials", to: "/admin/materials" },
          { label: grade?.name ?? "Grade" },
        ]}
      />
      <div className="back-row">
        <Link to="/admin/materials" className="btn btn--matte btn--sm">
          ← Back to materials
        </Link>
      </div>
      <header className="page-head">
        <p className="kicker">{grade?.name ?? "…"} · subjects</p>
        <h1>Subjects</h1>
        <p>Open a subject to browse units (topics) and lesson or quiz status.</p>
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
      {grade && (
        <div className="grid grid--2">
          {grade.subjects.map((subject) => {
            const topicCount = countTopics(subject);
            return (
              <Link
                key={subject.id}
                to={`/admin/materials/grades/${grade.key}/subjects/${subject.id}`}
                className="card"
              >
                <h2>{subject.name}</h2>
                <p>{subject.blurb}</p>
                <div className="meta-row">
                  <span className="chip">{subject.code}</span>
                  <span className="badge badge--ok">{topicCount} published</span>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

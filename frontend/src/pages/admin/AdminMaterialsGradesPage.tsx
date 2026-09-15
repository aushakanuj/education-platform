import { Link } from "react-router-dom";

import { Crumbs } from "../../components/Crumbs";
import { gradeSummary } from "../../lib/adminCurriculumLive";
import { useAdminDirectory } from "../../lib/useAdminDirectory";

export function AdminMaterialsGradesPage() {
  const { grades, loading, error } = useAdminDirectory();

  return (
    <div className="admin-materials">
      <Crumbs parts={[{ label: "Materials" }]} />
      <header className="page-head">
        <p className="kicker">Curriculum browser · live published catalog</p>
        <h1>Materials</h1>
        <p>Browse published curriculum by grade. Upload a new topic PDF from a subject's Topics page.</p>
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
      {!loading && !error && grades && grades.length === 0 && (
        <p className="muted" role="status">
          No published grades in the learning directory yet.
        </p>
      )}
      {!loading && !error && grades && grades.length > 0 && (
        <div className="grade-grid" role="list">
          {grades.map((grade) => {
            const summary = gradeSummary(grade);
            return (
              <Link
                key={grade.key}
                to={`/admin/materials/grades/${grade.key}`}
                className="card grade-grid__card"
                role="listitem"
              >
                <p className="kicker">Grade</p>
                <h2>{grade.number ?? grade.name}</h2>
                <p>
                  {summary.subjects} subjects · {summary.topics} published topics
                </p>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

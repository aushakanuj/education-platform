import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { Crumbs } from "../../components/Crumbs";
import { CurriculumMaterialUpload } from "../../components/CurriculumMaterialUpload";
import { gradeSummary, type AdminGrade } from "../../lib/adminCurriculumLive";
import { useAdminDirectory } from "../../lib/useAdminDirectory";

function flattenSubtopicOptions(grades: AdminGrade[]) {
  const options: { id: string; label: string }[] = [];
  for (const grade of grades) {
    for (const subject of grade.subjects) {
      for (const topic of subject.topics) {
        for (const subtopic of topic.subtopics) {
          options.push({
            id: subtopic.id,
            label: `${grade.name} · ${subject.name} · ${topic.title} · ${subtopic.title}`,
          });
        }
      }
    }
  }
  return options;
}

export function AdminMaterialsGradesPage() {
  const { grades, loading, error } = useAdminDirectory();
  const [showUpload, setShowUpload] = useState(false);
  const subtopicOptions = useMemo(
    () => (grades ? flattenSubtopicOptions(grades) : []),
    [grades],
  );

  return (
    <div className="admin-materials">
      <Crumbs parts={[{ label: "Materials" }]} />
      <header className="page-head page-head--with-actions">
        <div>
          <p className="kicker">Curriculum browser · live published catalog</p>
          <h1>Materials</h1>
          <p>
            Browse published curriculum by grade. Upload a lesson PDF to enqueue async ingest for a
            subtopic.
          </p>
        </div>
        <div className="page-head__actions">
          <button
            type="button"
            className="btn btn--outline"
            aria-expanded={showUpload}
            aria-controls="materials-upload-panel"
            onClick={() => setShowUpload((open) => !open)}
          >
            Upload
          </button>
        </div>
      </header>

      {showUpload && (
        <section
          id="materials-upload-panel"
          className="panel admin-materials__upload"
          aria-label="Upload curriculum PDF"
        >
          {loading && (
            <p className="muted" role="status">
              Loading subtopics for upload…
            </p>
          )}
          {error && (
            <p className="form__error" role="alert">
              {error}
            </p>
          )}
          {!loading && !error && subtopicOptions.length === 0 && (
            <p className="muted" role="status">
              No subtopics available yet. Seed curriculum, then retry upload.
            </p>
          )}
          {!loading && !error && subtopicOptions.length > 0 && (
            <CurriculumMaterialUpload subtopicOptions={subtopicOptions} />
          )}
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

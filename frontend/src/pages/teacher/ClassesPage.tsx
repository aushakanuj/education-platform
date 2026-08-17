import { Link } from "react-router-dom";

import { Crumbs } from "../../components/Crumbs";
import { useTeacherClasses } from "../../lib/useTeacherClasses";

export function ClassesPage() {
  const { loading, error, classes, scopeDescription } = useTeacherClasses();

  return (
    <>
      <Crumbs parts={[{ label: "My classes" }]} />
      <header className="page-head">
        <p className="kicker">Teacher · assignments</p>
        <h1>My classes</h1>
        <p>
          Sections where you have a teaching assignment. Open a class for roster and subject
          materials.
        </p>
        {scopeDescription && (
          <p className="progress-label">Showing: {scopeDescription.toLowerCase()}</p>
        )}
      </header>

      {loading && <div className="banner banner--info">Loading your classes…</div>}

      {error && (
        <div className="banner banner--warning" role="alert">
          {error}
        </div>
      )}

      {!loading && !error && classes.length === 0 && (
        <div className="banner banner--info" role="status">
          You have no teaching assignments in the current term. If that looks wrong, an
          administrator can check your assignments.
        </div>
      )}

      <div className="grid grid--2 teacher-class-grid">
        {classes.map((entry) => (
          <Link
            key={entry.id}
            to={`/teacher/classes/${entry.id}`}
            className="card teacher-class-card"
          >
            <div className="teacher-class-card__top">
              <h2>
                {entry.gradeName} · {entry.sectionName}
              </h2>
            </div>
            <p>
              {entry.academicPeriod} · {entry.subjects.join(", ")}
            </p>
            <div className="progress-label">
              {entry.students.length} student{entry.students.length === 1 ? "" : "s"} ·{" "}
              {entry.subjects.length} subject{entry.subjects.length === 1 ? "" : "s"}
            </div>
            <div className="meta-row">
              <span className="badge badge--info">{entry.gradeName}</span>
              <span className="badge">Section {entry.sectionName}</span>
            </div>
          </Link>
        ))}
      </div>
    </>
  );
}

import { Link, Navigate, useParams } from "react-router-dom";

import { Crumbs } from "../../components/Crumbs";
import { getTeacherSection } from "../../mocks/teacherAssignments";

export function SectionPage() {
  const { sectionId = "" } = useParams();
  const section = getTeacherSection(sectionId);

  if (!section) {
    return <Navigate to="/teacher" replace />;
  }

  const activeCount = section.roster.filter((s) => s.status === "active").length;

  return (
    <>
      <Crumbs
        parts={[
          { label: "My classes", to: "/teacher" },
          { label: section.label },
        ]}
      />
      <header className="page-head">
        <p className="kicker">{section.academicPeriod} · teaching assignment</p>
        <h1>{section.label}</h1>
        <p>Roster and the subjects you teach in this section.</p>
      </header>

      <div className="teacher-section-hub">
        <Link
          to={`/teacher/classes/${section.id}/students`}
          className="card teacher-hub-card"
        >
          <h2>Student roster</h2>
          <p>
            {activeCount} active of {section.roster.length} enrolled
          </p>
          <div className="meta-row">
            <span className="badge badge--info">Roster</span>
          </div>
        </Link>

        <section className="teacher-hub-subjects" aria-labelledby="taught-subjects-heading">
          <div className="topics-section__head">
            <h2 id="taught-subjects-heading">Subjects you teach</h2>
            <p>Open materials and a light class progress strip for each assignment.</p>
          </div>
          <div className="grid grid--2">
            {section.subjects.map((subject) => (
              <Link
                key={subject.id}
                to={`/teacher/classes/${section.id}/subjects/${subject.id}`}
                className="card"
              >
                <h3>{subject.name}</h3>
                <p>{subject.blurb}</p>
                <div className="progress-label">
                  {subject.progress.pct}% · {subject.topics.length} units
                </div>
                <div
                  className={`progress ${subject.progress.pct >= 100 ? "progress--complete" : "progress--in-progress"}`}
                  aria-hidden="true"
                >
                  <span style={{ width: `${subject.progress.pct}%` }} />
                </div>
                <div className="meta-row">
                  <span className="badge badge--info">Materials</span>
                  <span className="badge">{subject.code}</span>
                </div>
              </Link>
            ))}
          </div>
        </section>
      </div>
    </>
  );
}

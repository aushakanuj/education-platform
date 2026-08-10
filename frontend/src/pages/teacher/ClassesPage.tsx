import { Link } from "react-router-dom";

import { Crumbs } from "../../components/Crumbs";
import { TEACHER_SECTIONS } from "../../mocks/teacherAssignments";

export function ClassesPage() {
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
      </header>

      <div className="grid grid--2 teacher-class-grid">
        {TEACHER_SECTIONS.map((section) => {
          const subjectNames = section.subjects.map((s) => s.name).join(", ");
          return (
            <Link
              key={section.id}
              to={`/teacher/classes/${section.id}`}
              className="card teacher-class-card"
            >
              <div className="teacher-class-card__top">
                <h2>{section.label}</h2>
              </div>
              <p>
                {section.academicPeriod} · {subjectNames}
              </p>
              <div className="progress-label">
                {section.roster.filter((s) => s.status === "active").length} active students ·{" "}
                {section.subjects.length} subject
                {section.subjects.length === 1 ? "" : "s"}
              </div>
              <div className="meta-row">
                <span className="badge badge--info">{section.gradeName}</span>
                <span className="badge">Section {section.sectionCode}</span>
              </div>
            </Link>
          );
        })}
      </div>
    </>
  );
}

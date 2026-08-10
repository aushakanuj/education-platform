import { Link, Navigate, useParams } from "react-router-dom";

import { Crumbs } from "../../components/Crumbs";
import {
  getTeacherSection,
  rosterStatusLabel,
  type RosterStatus,
} from "../../mocks/teacherAssignments";

function statusBadgeClass(status: RosterStatus): string {
  switch (status) {
    case "active":
      return "badge badge--ok";
    case "inactive":
      return "badge badge--warn";
    case "transferred":
      return "badge badge--locked";
  }
}

export function RosterPage() {
  const { sectionId = "" } = useParams();
  const section = getTeacherSection(sectionId);

  if (!section) {
    return <Navigate to="/teacher" replace />;
  }

  return (
    <>
      <Crumbs
        parts={[
          { label: "My classes", to: "/teacher" },
          { label: section.label, to: `/teacher/classes/${section.id}` },
          { label: "Students" },
        ]}
      />
      <div className="back-row">
        <Link
          to={`/teacher/classes/${section.id}`}
          className="btn btn--outline btn--sm"
        >
          ← Back to section
        </Link>
      </div>
      <header className="page-head">
        <p className="kicker">{section.label} · roster</p>
        <h1>Students</h1>
        <p>Fixture roster for students in this section.</p>
      </header>

      <div className="teacher-roster" role="table" aria-label={`Roster for ${section.label}`}>
        <div className="teacher-roster__head" role="row">
          <span role="columnheader">Roll</span>
          <span role="columnheader">Name</span>
          <span role="columnheader">Status</span>
        </div>
        {section.roster.map((student) => (
          <div key={student.id} className="teacher-roster__row" role="row">
            <span className="teacher-roster__roll" role="cell">
              {student.rollNo}
            </span>
            <span className="teacher-roster__name" role="cell">
              {student.fullName}
            </span>
            <span role="cell">
              <span className={statusBadgeClass(student.status)}>
                {rosterStatusLabel(student.status)}
              </span>
            </span>
          </div>
        ))}
      </div>
    </>
  );
}

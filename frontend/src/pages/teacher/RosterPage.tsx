import { Navigate, useParams } from "react-router-dom";

import { Crumbs } from "../../components/Crumbs";
import { averageMastery, findClass, useTeacherClasses } from "../../lib/useTeacherClasses";

/** Below this, a teacher is not eligible to sit the exam. Mirrors the early-warning rule. */
const ATTENDANCE_THRESHOLD = 75;
const MASTERY_CONCERN = 60;

export function RosterPage() {
  const { sectionId = "" } = useParams();
  const { loading, error, classes } = useTeacherClasses();

  if (loading) {
    return <div className="banner banner--info">Loading roster…</div>;
  }
  if (error) {
    return (
      <div className="banner banner--warning" role="alert">
        {error}
      </div>
    );
  }

  const entry = findClass(classes, sectionId);
  if (!entry) {
    return <Navigate to="/teacher" replace />;
  }

  const label = `${entry.gradeName} · ${entry.sectionName}`;

  return (
    <>
      <Crumbs
        parts={[
          { label: "My classes", to: "/teacher" },
          { label, to: `/teacher/classes/${entry.id}` },
          { label: "Students" },
        ]}
      />
      <header className="page-head">
        <p className="kicker">{label} · roster</p>
        <h1>Students</h1>
        <p>
          Mastery is averaged across {entry.subjects.join(" and ")} — the subject
          {entry.subjects.length === 1 ? "" : "s"} you teach this section.
        </p>
      </header>

      <div className="teacher-roster" role="table" aria-label={`Roster for ${label}`}>
        <div className="teacher-roster__head" role="row">
          <span role="columnheader">Roll</span>
          <span role="columnheader">Name</span>
          <span role="columnheader">Mastery</span>
          <span role="columnheader">Attendance</span>
        </div>
        {entry.students.map((student) => {
          const mastery = averageMastery(student);
          const attendance = student.attendancePercent;
          return (
            <div key={student.id} className="teacher-roster__row" role="row">
              <span className="teacher-roster__roll" role="cell">
                {student.identifier}
              </span>
              <span className="teacher-roster__name" role="cell">
                {student.fullName}
              </span>
              <span role="cell">
                {mastery === null ? (
                  <span className="badge">No quizzes yet</span>
                ) : (
                  <span className={mastery < MASTERY_CONCERN ? "badge badge--warn" : "badge badge--ok"}>
                    {mastery.toFixed(0)}%
                  </span>
                )}
              </span>
              <span role="cell">
                {attendance === null ? (
                  <span className="badge">Not recorded</span>
                ) : (
                  <span
                    className={
                      attendance < ATTENDANCE_THRESHOLD ? "badge badge--warn" : "badge badge--ok"
                    }
                  >
                    {attendance.toFixed(0)}%
                  </span>
                )}
              </span>
            </div>
          );
        })}
      </div>
    </>
  );
}

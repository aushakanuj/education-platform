import { Link, Navigate, useParams } from "react-router-dom";

import { Crumbs } from "../../components/Crumbs";
import { useLearningDirectory } from "../../lib/useLearningDirectory";
import { findClass, useTeacherClasses } from "../../lib/useTeacherClasses";

export function SectionPage() {
  const { sectionId = "" } = useParams();
  const { loading, error, classes } = useTeacherClasses();
  const directoryState = useLearningDirectory();

  if (loading || directoryState.loading) {
    return <div className="banner banner--info">Loading…</div>;
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
      <Crumbs parts={[{ label: "My classes", to: "/teacher" }, { label }]} />
      <header className="page-head">
        <p className="kicker">{entry.academicPeriod} · teaching assignment</p>
        <h1>{label}</h1>
        <p>Roster and the subjects you teach in this section.</p>
      </header>

      <div className="teacher-section-hub">
        <Link to={`/teacher/classes/${entry.id}/students`} className="card teacher-hub-card">
          <h2>Student roster</h2>
          <p>
            {entry.students.length} student{entry.students.length === 1 ? "" : "s"} enrolled
          </p>
          <div className="meta-row">
            <span className="badge badge--info">Roster</span>
          </div>
        </Link>

        <section className="teacher-hub-subjects" aria-labelledby="taught-subjects-heading">
          <div className="topics-section__head">
            <h2 id="taught-subjects-heading">Subjects you teach</h2>
            <p>
              Only the subjects you are assigned to in this section. Other subjects these
              students take are not yours to see.
            </p>
          </div>
          {directoryState.error && (
            <div className="banner banner--warning" role="alert">
              {directoryState.error}
            </div>
          )}
          <div className="grid grid--2">
            {entry.subjects.map((subject) => {
              const marks = entry.students
                .flatMap((student) => student.bySubject)
                .filter((s) => s.subject === subject && s.quizzesTaken > 0);
              const average = marks.length
                ? Math.round(marks.reduce((sum, s) => sum + s.masteryPercent, 0) / marks.length)
                : 0;
              const node = directoryState.directory?.subjects.find(
                (row) => row.name === subject && row.grade_name === entry.gradeName,
              );
              const body = (
                <>
                  <h3>{subject}</h3>
                  <p>
                    {marks.length} of {entry.students.length} students have attempted a quiz.
                  </p>
                  <div className="progress-label">{average}% average mastery</div>
                  <div
                    className={`progress ${average >= 60 ? "progress--complete" : "progress--in-progress"}`}
                    aria-hidden="true"
                  >
                    <span style={{ width: `${average}%` }} />
                  </div>
                  <div className="meta-row">
                    <span className="badge badge--info">{entry.gradeName}</span>
                    {node && <span className="badge">Materials</span>}
                  </div>
                </>
              );
              if (node) {
                return (
                  <Link
                    key={subject}
                    to={`/teacher/classes/${entry.id}/subjects/${node.id}`}
                    className="card"
                  >
                    {body}
                  </Link>
                );
              }
              return (
                <div key={subject} className="card">
                  {body}
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </>
  );
}

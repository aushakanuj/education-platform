import { useMemo, useState } from "react";
import { Navigate, useParams } from "react-router-dom";

import { Crumbs } from "../../components/Crumbs";
import {
  averageMastery,
  findClass,
  useTeacherClasses,
  type TeacherClassStudent,
} from "../../lib/useTeacherClasses";

/** Below this a student is not eligible to sit the exam. Mirrors the early-warning rule. */
const ATTENDANCE_THRESHOLD = 75;
const MASTERY_CONCERN = 60;

type SortKey = "name" | "mastery" | "attendance";

/** Nulls last whichever way the column is sorted — "no data" is not a low score. */
function compareNullable(a: number | null, b: number | null): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return a - b;
}

export function RosterPage() {
  const { sectionId = "" } = useParams();
  const { loading, error, classes } = useTeacherClasses();
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [query, setQuery] = useState("");

  const entry = findClass(classes, sectionId);

  const students = useMemo(() => {
    if (!entry) return [];
    const needle = query.trim().toLowerCase();
    const filtered = needle
      ? entry.students.filter(
          (student) =>
            student.fullName.toLowerCase().includes(needle) ||
            student.identifier.toLowerCase().includes(needle),
        )
      : entry.students;

    const sorted = [...filtered];
    if (sortKey === "name") {
      sorted.sort((a, b) => a.fullName.localeCompare(b.fullName));
    } else if (sortKey === "mastery") {
      sorted.sort((a, b) => compareNullable(averageMastery(a), averageMastery(b)));
    } else {
      sorted.sort((a, b) => compareNullable(a.attendancePercent, b.attendancePercent));
    }
    return sorted;
  }, [entry, query, sortKey]);

  const needsAttention = useMemo(() => {
    if (!entry) return { attendance: 0, mastery: 0 };
    return {
      attendance: entry.students.filter(
        (s) => s.attendancePercent !== null && s.attendancePercent < ATTENDANCE_THRESHOLD,
      ).length,
      mastery: entry.students.filter((s) => {
        const m = averageMastery(s);
        return m !== null && m < MASTERY_CONCERN;
      }).length,
    };
  }, [entry]);

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
        <h1>
          {entry.students.length} student{entry.students.length === 1 ? "" : "s"}
        </h1>
        <p>
          Mastery is averaged across {entry.subjects.join(" and ")} — the subject
          {entry.subjects.length === 1 ? "" : "s"} you teach this section.
        </p>
      </header>

      {(needsAttention.attendance > 0 || needsAttention.mastery > 0) && (
        <div className="banner banner--warning" role="status">
          <strong>Worth a look:</strong>{" "}
          {needsAttention.attendance > 0 && (
            <>
              {needsAttention.attendance} below {ATTENDANCE_THRESHOLD}% attendance
            </>
          )}
          {needsAttention.attendance > 0 && needsAttention.mastery > 0 && " · "}
          {needsAttention.mastery > 0 && (
            <>
              {needsAttention.mastery} below {MASTERY_CONCERN}% mastery
            </>
          )}
        </div>
      )}

      <div className="roster-controls">
        <div className="field">
          <label className="field__label" htmlFor="roster-search">
            Find a student
          </label>
          <input
            id="roster-search"
            className="field__input"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Name or roll number"
          />
        </div>
        <div className="field">
          <span className="field__label">Sort by</span>
          <div className="meta-row" role="group" aria-label="Sort by">
            {(
              [
                ["name", "Name"],
                ["mastery", "Lowest mastery"],
                ["attendance", "Lowest attendance"],
              ] as [SortKey, string][]
            ).map(([key, text]) => (
              <button
                key={key}
                type="button"
                className={`badge ${sortKey === key ? "badge--info" : ""}`}
                aria-pressed={sortKey === key}
                onClick={() => setSortKey(key)}
              >
                {text}
              </button>
            ))}
          </div>
        </div>
      </div>

      {students.length === 0 ? (
        <div className="banner banner--info" role="status">
          No student matches “{query}”.
        </div>
      ) : (
        <div className="teacher-roster" role="table" aria-label={`Roster for ${label}`}>
          <div className="teacher-roster__head" role="row">
            <span role="columnheader">Roll</span>
            <span role="columnheader">Name</span>
            <span role="columnheader">Mastery</span>
            <span role="columnheader">Attendance</span>
          </div>
          {students.map((student) => (
            <RosterRow key={student.id} student={student} />
          ))}
        </div>
      )}
    </>
  );
}

function RosterRow({ student }: { student: TeacherClassStudent }) {
  const mastery = averageMastery(student);
  const attendance = student.attendancePercent;

  return (
    <div className="teacher-roster__row" role="row">
      <span className="teacher-roster__roll" role="cell">
        {student.identifier}
      </span>
      <span className="teacher-roster__name" role="cell">
        {student.fullName}
        {student.bySubject.length > 1 && (
          <span className="roster-subjects">
            {student.bySubject
              .map((s) => `${s.subject} ${s.quizzesTaken > 0 ? `${s.masteryPercent.toFixed(0)}%` : "—"}`)
              .join(" · ")}
          </span>
        )}
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
}

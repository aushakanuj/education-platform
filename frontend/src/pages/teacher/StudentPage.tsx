import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Crumbs } from "../../components/Crumbs";
import { fetchStudentDetail, type StudentAttempt, type StudentDetail } from "../../api/insights";

/** Below this a student is not eligible to sit the exam. Mirrors the roster's rule. */
const ATTENDANCE_THRESHOLD = 75;
const MASTERY_CONCERN = 60;

/** How many recent quizzes count as "lately". */
const TREND_WINDOW = 3;
/** Fewer than this behind them and there is nothing to compare against. */
const TREND_EARLIER_MINIMUM = 2;
/** Below this a move is well inside normal quiz-to-quiz variation. */
const TREND_MARGIN = 5;

function formatDay(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

type Trend = {
  direction: "up" | "down";
  recent: number;
  earlier: number;
  /** Both counts, so the banner can state the size of what it compared. */
  recentCount: number;
  earlierCount: number;
} | null;

/**
 * The last few quizzes against everything before them.
 *
 * Deliberately plain arithmetic on what the teacher can already see in the table below,
 * not a risk score: the rules that decide who is at risk are Rahul's task 3.1, and this
 * should be replaced by them rather than quietly become a second opinion. It says nothing
 * unless the move clears `TREND_MARGIN`, because a 2% wobble is not a direction.
 *
 * The earlier group is whatever remains rather than a matching window, and the banner
 * names both counts. A fixed 3-against-3 needed six quizzes, which no student in a term
 * this length has yet -- a comparison nobody ever sees is worse than an uneven one that
 * says how uneven it is.
 */
export function attemptTrend(attempts: StudentAttempt[]): Trend {
  const scored = attempts.filter((a) => a.score_percent !== null);
  if (scored.length < TREND_WINDOW + TREND_EARLIER_MINIMUM) return null;

  // `attempts` arrives newest first.
  const mean = (window: StudentAttempt[]) =>
    window.reduce((sum, a) => sum + (a.score_percent ?? 0), 0) / window.length;
  const recentGroup = scored.slice(0, TREND_WINDOW);
  const earlierGroup = scored.slice(TREND_WINDOW);
  const recent = mean(recentGroup);
  const earlier = mean(earlierGroup);

  if (Math.abs(recent - earlier) < TREND_MARGIN) return null;
  return {
    direction: recent > earlier ? "up" : "down",
    recent,
    earlier,
    recentCount: recentGroup.length,
    earlierCount: earlierGroup.length,
  };
}

export function StudentPage() {
  const { sectionId = "", studentId = "" } = useParams();
  const [student, setStudent] = useState<StudentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchStudentDetail(studentId)
      .then((detail) => {
        if (cancelled) return;
        setStudent(detail);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(
          err instanceof Error ? err.message : "That student is not one of yours to open.",
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [studentId]);

  const trend = useMemo(() => attemptTrend(student?.attempts ?? []), [student]);

  if (loading) {
    return <div className="banner banner--info">Loading student…</div>;
  }
  if (error || !student) {
    return (
      <>
        <Crumbs
          parts={[
            { label: "My classes", to: "/teacher" },
            { label: "Students", to: `/teacher/classes/${sectionId}/students` },
            { label: "Not found" },
          ]}
        />
        <div className="banner banner--warning" role="alert">
          {error ?? "That student is not one of yours to open."}
        </div>
      </>
    );
  }

  const classLabel = `${student.grade} · ${student.section ?? "Unassigned"}`;
  const attendance = student.attendance_percent;

  return (
    <>
      <Crumbs
        parts={[
          { label: "My classes", to: "/teacher" },
          { label: classLabel, to: `/teacher/classes/${sectionId}` },
          { label: "Students", to: `/teacher/classes/${sectionId}/students` },
          { label: student.full_name },
        ]}
      />
      <header className="page-head">
        <p className="kicker">
          {student.student_identifier} · {classLabel} · {student.academic_period}
        </p>
        <h1>{student.full_name}</h1>
        <p>
          {student.subjects.length === 1
            ? "The subject you teach this student."
            : `The ${student.subjects.length} subjects you teach this student.`}{" "}
          Anything they study with another teacher is not shown here.
        </p>
      </header>

      <div className="student-panels">
        <section className="card" aria-labelledby="attendance-heading">
          <h2 id="attendance-heading">Attendance</h2>
          {attendance === null ? (
            <p className="progress-label">No attendance recorded this term.</p>
          ) : (
            <>
              <div className="student-figure">
                <span
                  className={
                    attendance < ATTENDANCE_THRESHOLD
                      ? "student-figure__value is-concern"
                      : "student-figure__value"
                  }
                >
                  {attendance.toFixed(0)}%
                </span>
                <span className="progress-label">
                  {student.days_present} of {student.days_counted} days
                </span>
              </div>
              {attendance < ATTENDANCE_THRESHOLD && (
                <p className="progress-label">
                  Below the {ATTENDANCE_THRESHOLD}% needed to sit the end-of-term exam.
                </p>
              )}
            </>
          )}

          {student.absences.length > 0 && (
            <>
              <h3 className="student-subhead">Recent days missed</h3>
              <ul className="student-absences">
                {student.absences.map((absence) => (
                  <li key={`${absence.on_date}-${absence.status}`}>
                    <span>{formatDay(absence.on_date)}</span>
                    <span className="badge">{absence.status}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>

        <section aria-labelledby="subjects-heading">
          <div className="topics-section__head">
            <h2 id="subjects-heading">How they are doing</h2>
          </div>
          <div className="student-subject-list">
            {student.subjects.map((standing) => {
              const mastery = Math.round(standing.mastery_percent);
              const attempted = standing.quizzes_taken > 0;
              return (
                <article key={standing.subject} className="card">
                  <div className="meta-row">
                    <h3>{standing.subject}</h3>
                  </div>
                  {attempted ? (
                    <>
                      <div className="progress-label">{mastery}% mastery</div>
                      <div
                        className={`progress ${
                          mastery >= MASTERY_CONCERN ? "progress--complete" : "progress--in-progress"
                        }`}
                        aria-hidden="true"
                      >
                        <span style={{ width: `${mastery}%` }} />
                      </div>
                      <p className="progress-label">
                        Passed {standing.quizzes_passed} of {standing.quizzes_taken} quizzes ·
                        last attempt {formatDay(standing.last_attempt_at)}
                      </p>
                    </>
                  ) : (
                    <p className="progress-label">No quizzes attempted yet.</p>
                  )}
                  <p className="progress-label">
                    {standing.lessons_completed} of {standing.lessons_started} lessons finished
                  </p>
                </article>
              );
            })}
          </div>
        </section>
      </div>

      <section aria-labelledby="history-heading">
        <div className="topics-section__head">
          <h2 id="history-heading">Quiz history</h2>
          <p>
            {student.attempts.length === 0
              ? "Nothing submitted yet in your subjects."
              : `The last ${student.attempts.length} quizzes they finished in your subjects, newest first.`}
          </p>
        </div>

        {trend && (
          <div
            className={`banner ${trend.direction === "down" ? "banner--warning" : "banner--info"}`}
            role="status"
          >
            <strong>{trend.direction === "down" ? "Slipping:" : "Improving:"}</strong> last{" "}
            {trend.recentCount} quizzes averaged {trend.recent.toFixed(0)}%, against{" "}
            {trend.earlier.toFixed(0)}% over the {trend.earlierCount} before.
          </div>
        )}

        {student.attempts.length > 0 && (
          <div className="table-scroll">
            <table className="data-table student-history">
              <thead>
                <tr>
                  <th scope="col">Submitted</th>
                  <th scope="col">Subject</th>
                  <th scope="col">Quiz</th>
                  <th scope="col">Score</th>
                  <th scope="col">Result</th>
                </tr>
              </thead>
              <tbody>
                {student.attempts.map((attempt) => (
                  <tr key={attempt.attempt_id}>
                    <td>{formatDay(attempt.submitted_at)}</td>
                    <td>{attempt.subject}</td>
                    <td>
                      {attempt.quiz_title}
                      {attempt.attempt_number > 1 && (
                        <span className="badge"> attempt {attempt.attempt_number}</span>
                      )}
                    </td>
                    <td>
                      {attempt.score_percent === null
                        ? "—"
                        : `${Math.round(attempt.score_percent)}%`}
                    </td>
                    <td>
                      {attempt.passed === null ? (
                        <span className="badge">Not marked</span>
                      ) : (
                        <span className={attempt.passed ? "badge badge--ok" : "badge badge--warn"}>
                          {attempt.passed ? "Passed" : "Not passed"}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div className="meta-row">
        <Link className="badge badge--info" to={`/teacher/classes/${sectionId}/students`}>
          ← Back to the roster
        </Link>
      </div>
    </>
  );
}

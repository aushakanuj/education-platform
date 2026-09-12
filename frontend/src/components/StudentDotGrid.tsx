import { Link } from "react-router-dom";

import { tierFor, type TierStudent } from "../lib/teacherAnalytics";

/**
 * One square per student, strongest first, coloured by tier.
 *
 * A stacked bar says "14 strong, 10 average"; this says the same thing while keeping the
 * class a set of individuals rather than two lengths. Each square is a link to that
 * student, so the shape of the class and the way into any one of them are the same object.
 */
export function StudentDotGrid({
  sectionId,
  students,
}: {
  sectionId: string;
  students: TierStudent[];
}) {
  if (students.length === 0) return null;

  return (
    <div className="dot-grid">
      {students.map((student) => {
        const description = `${student.fullName} — ${
          student.mastery === null ? "no attempts yet" : `${Math.round(student.mastery)}% mastery`
        }`;
        return (
          <Link
            key={student.studentId}
            to={`/teacher/classes/${sectionId}/students/${student.studentId}`}
            className={`dot-grid__dot dot-grid__dot--${tierFor(student.mastery)}`}
            title={description}
            aria-label={description}
          />
        );
      })}
    </div>
  );
}

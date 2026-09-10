import type { AtRiskFlag } from "../api/atRisk";
import { averageMastery, type TeacherClass, type TeacherClassStudent } from "./useTeacherClasses";

/** A student's standing on the mastery scale, used for both a single ring and a section's
 * distribution bar. Deliberately four buckets, not three: a student with zero attempts is a
 * different situation from one who attempted and scored below 50%, and hiding that
 * difference would make an empty section look like a struggling one. */
export type PerformanceTier = "strong" | "average" | "struggling" | "not_started";

export function tierFor(mastery: number | null): PerformanceTier {
  if (mastery === null) return "not_started";
  if (mastery >= 70) return "strong";
  if (mastery >= 50) return "average";
  return "struggling";
}

/** Plain-language rule for each tier, so "why is this student in this group" never requires
 * asking someone -- it's printed right next to the group. Mirrors the thresholds above. */
export const TIER_BASIS: Record<PerformanceTier, string> = {
  strong: "Averaging 70% or higher across the subjects they've attempted.",
  average: "Averaging 50-69% across the subjects they've attempted.",
  struggling: "Averaging below 50% across the subjects they've attempted.",
  not_started: "No graded quiz attempts yet in any subject you teach them.",
};

export type TierStudent = { studentId: string; fullName: string; mastery: number | null };

/** Below this, a student cannot sit the end-of-term exam -- see StudentPage.tsx's
 * EXAM_ELIGIBILITY_ATTENDANCE. Kept as its own constant here rather than imported, since a
 * dashboard summary and an eligibility rule are different concerns that happen to share a
 * number today. */
const ATTENDANCE_SPOTLIGHT_THRESHOLD = 75;

export type LowAttendanceStudent = {
  studentId: string;
  fullName: string;
  attendancePercent: number;
};

export type SectionAnalytics = {
  sectionId: string;
  sectionName: string;
  gradeName: string;
  academicPeriod: string;
  studentCount: number;
  averageMastery: number | null;
  averageAttendance: number | null;
  distribution: Record<PerformanceTier, number>;
  studentsByTier: Record<PerformanceTier, TierStudent[]>;
  atRiskCounts: { urgent: number; attention: number; monitor: number; total: number };
  lowAttendance: LowAttendanceStudent[];
};

function average(values: number[]): number | null {
  if (values.length === 0) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function hasAttendance(
  student: TeacherClassStudent,
): student is TeacherClassStudent & { attendancePercent: number } {
  return student.attendancePercent !== null;
}

/**
 * One section's worth of analytics, computed entirely from data the teacher already legally
 * sees -- the same rows `useTeacherClasses` and `useAtRiskFlags` already fetched through the
 * server's own Scope. Nothing here queries anything new or re-derives who may see what; it
 * only summarises rows that were already narrowed before they got here.
 */
export function computeSectionAnalytics(
  classes: TeacherClass[],
  flags: AtRiskFlag[],
): SectionAnalytics[] {
  return classes.map((section) => {
    const studentIds = new Set(section.students.map((student) => student.id));

    const masteries = section.students
      .map((student) => averageMastery(student))
      .filter((value): value is number => value !== null);

    const distribution: Record<PerformanceTier, number> = {
      strong: 0,
      average: 0,
      struggling: 0,
      not_started: 0,
    };
    const studentsByTier: Record<PerformanceTier, TierStudent[]> = {
      strong: [],
      average: [],
      struggling: [],
      not_started: [],
    };
    for (const student of section.students) {
      const mastery = averageMastery(student);
      const tier = tierFor(mastery);
      distribution[tier] += 1;
      studentsByTier[tier].push({ studentId: student.id, fullName: student.fullName, mastery });
    }
    for (const tier of Object.keys(studentsByTier) as PerformanceTier[]) {
      studentsByTier[tier].sort((a, b) => (b.mastery ?? -1) - (a.mastery ?? -1));
    }

    const sectionFlags = flags.filter((flag) => studentIds.has(flag.student_id));

    const lowAttendance = section.students
      .filter(hasAttendance)
      .filter((student) => student.attendancePercent < ATTENDANCE_SPOTLIGHT_THRESHOLD)
      .sort((a, b) => a.attendancePercent - b.attendancePercent)
      .slice(0, 5)
      .map((student) => ({
        studentId: student.id,
        fullName: student.fullName,
        attendancePercent: student.attendancePercent,
      }));

    return {
      sectionId: section.id,
      sectionName: section.sectionName,
      gradeName: section.gradeName,
      academicPeriod: section.academicPeriod,
      studentCount: section.students.length,
      averageMastery: average(masteries),
      averageAttendance: average(
        section.students.filter(hasAttendance).map((student) => student.attendancePercent),
      ),
      distribution,
      studentsByTier,
      atRiskCounts: {
        urgent: sectionFlags.filter((flag) => flag.tier === "urgent").length,
        attention: sectionFlags.filter((flag) => flag.tier === "attention").length,
        monitor: sectionFlags.filter((flag) => flag.tier === "monitor").length,
        total: sectionFlags.length,
      },
      lowAttendance,
    };
  });
}

/** One subject's average across a given set of students, counting only those who have
 * actually attempted it -- the same rule as `subjectAverages`, asked one subject at a time
 * so a grid can fill a specific cell. */
function subjectAverageFor(students: TeacherClassStudent[], subject: string): number | null {
  return average(
    students.flatMap((student) =>
      student.bySubject
        .filter((entry) => entry.subject === subject && entry.quizzesTaken > 0)
        .map((entry) => entry.masteryPercent),
    ),
  );
}

/** Every student's own cross-subject average, averaged -- one student, one vote, regardless
 * of how many subjects they happen to take. */
function overallAverageFor(students: TeacherClassStudent[]): number | null {
  return average(
    students.map(averageMastery).filter((value): value is number => value !== null),
  );
}

export type HeatmapRowKind = "section" | "grade" | "all";

export type HeatmapRow = {
  key: string;
  label: string;
  kind: HeatmapRowKind;
  /** Set only on a real section, so summary rows are not links to nowhere. */
  sectionId: string | null;
  studentCount: number;
  /** One value per entry in `Heatmap.subjects`, same order. Null where nothing was attempted. */
  cells: (number | null)[];
  overall: number | null;
};

export type Heatmap = { subjects: string[]; rows: HeatmapRow[] };

/**
 * The whole teaching load as one class-by-subject grid.
 *
 * This replaces three separate stacks of bars: comparing classes is now reading down the
 * last column, finding a weak subject is reading along the bottom row, and a grade's
 * combined standing is its own summary row. Summary rows are computed from their students
 * directly rather than by averaging the section averages above them, so a section of 30 and
 * a section of 12 cannot count equally.
 */
export function computeHeatmap(classes: TeacherClass[]): Heatmap {
  if (classes.length === 0) return { subjects: [], rows: [] };

  const everyStudent = classes.flatMap((section) => section.students);

  // Weakest subject first, matching the "what needs attention rises to the top" convention
  // used everywhere else on this page. Subjects with no attempts at all sort last.
  const subjects = [...new Set(classes.flatMap((section) => section.subjects))].sort(
    (a, b) =>
      (subjectAverageFor(everyStudent, a) ?? 101) - (subjectAverageFor(everyStudent, b) ?? 101) ||
      a.localeCompare(b),
  );

  const buildRow = (
    key: string,
    label: string,
    kind: HeatmapRowKind,
    sectionId: string | null,
    students: TeacherClassStudent[],
  ): HeatmapRow => ({
    key,
    label,
    kind,
    sectionId,
    studentCount: students.length,
    cells: subjects.map((subject) => subjectAverageFor(students, subject)),
    overall: overallAverageFor(students),
  });

  const byGrade = new Map<string, TeacherClass[]>();
  for (const section of classes) {
    byGrade.set(section.gradeName, [...(byGrade.get(section.gradeName) ?? []), section]);
  }

  const rows: HeatmapRow[] = [];
  for (const [gradeName, sections] of byGrade) {
    for (const section of sections) {
      rows.push(
        buildRow(
          section.id,
          `${section.gradeName} · ${section.sectionName}`,
          "section",
          section.id,
          section.students,
        ),
      );
    }
    // Only worth a row when it says something a single section's row did not.
    if (sections.length > 1) {
      rows.push(
        buildRow(
          `grade:${gradeName}`,
          `${gradeName} · all sections`,
          "grade",
          null,
          sections.flatMap((section) => section.students),
        ),
      );
    }
  }
  if (classes.length > 1) {
    rows.push(buildRow("all", "All your classes", "all", null, everyStudent));
  }

  return { subjects, rows };
}

/**
 * How strongly to tint a heatmap cell, as a percentage. Worse scores are deeper, so the eye
 * lands on the cell that needs a lesson replanned -- which is the panel's whole job.
 *
 * Deliberately an absolute scale, not one stretched to fit whatever spread happens to be on
 * screen: normalising to the visible range would paint a 69 as alarming next to a 73 merely
 * because nothing worse was in view, and a teacher would read that as a bigger problem than
 * it is. The trade is that a school whose classes genuinely all sit together looks evenly
 * tinted, which is the honest picture.
 *
 * The floor and cap keep a cell readable at both ends: text on an 80%-strength wash is hard
 * to read, and a 0% wash is not a heatmap.
 */
export function cellTintPercent(mastery: number): number {
  return Math.round(Math.min(78, Math.max(10, (100 - mastery) * 0.9)));
}

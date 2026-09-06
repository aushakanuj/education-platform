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

/** Below this, a student cannot sit the end-of-term exam -- see StudentPage.tsx's
 * EXAM_ELIGIBILITY_ATTENDANCE. Kept as its own constant here rather than imported, since a
 * dashboard summary and an eligibility rule are different concerns that happen to share a
 * number today. */
const ATTENDANCE_SPOTLIGHT_THRESHOLD = 75;

export type SubjectAverage = { subject: string; averageMastery: number };

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
  subjectAverages: SubjectAverage[];
  distribution: Record<PerformanceTier, number>;
  atRiskCounts: { urgent: number; attention: number; monitor: number; total: number };
  lowAttendance: LowAttendanceStudent[];
};

function average(values: number[]): number | null {
  if (values.length === 0) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function subjectAverages(students: TeacherClassStudent[]): SubjectAverage[] {
  const totals = new Map<string, { sum: number; count: number }>();
  for (const student of students) {
    for (const entry of student.bySubject) {
      if (entry.quizzesTaken === 0) continue;
      const bucket = totals.get(entry.subject) ?? { sum: 0, count: 0 };
      bucket.sum += entry.masteryPercent;
      bucket.count += 1;
      totals.set(entry.subject, bucket);
    }
  }
  return [...totals.entries()]
    .map(([subject, { sum, count }]) => ({ subject, averageMastery: sum / count }))
    .sort((a, b) => a.averageMastery - b.averageMastery);
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
    for (const student of section.students) {
      distribution[tierFor(averageMastery(student))] += 1;
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
      subjectAverages: subjectAverages(section.students),
      distribution,
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

/** The same subject averages as one section's, but rolled up across every section the
 * teacher teaches -- answers "which subject needs my attention across all my classes",
 * not just one class at a time. */
export function computeSubjectOverview(classes: TeacherClass[]): SubjectAverage[] {
  return subjectAverages(classes.flatMap((section) => section.students));
}

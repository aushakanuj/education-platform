import { useEffect, useMemo, useState } from "react";

import { fetchStudentInsights, type StudentInsightRow } from "../api/insights";

/**
 * A section the signed-in teacher is assigned to, with the subjects they teach in it.
 *
 * Built by grouping the register rather than by asking for "my classes": the server has
 * already removed everything outside the teacher's boundary, so whatever comes back *is*
 * their classes. Nothing here filters by identity, and nothing here should — that would be
 * a second permission rule living in the browser, where it can be edited.
 */
export type TeacherClass = {
  /** URL-safe key. Sections are named like "8A", so the name serves. */
  id: string;
  sectionName: string;
  gradeName: string;
  academicPeriod: string;
  subjects: string[];
  students: TeacherClassStudent[];
};

export type TeacherClassStudent = {
  id: string;
  fullName: string;
  identifier: string;
  attendancePercent: number | null;
  /** Mastery per subject, for the subjects this teacher may see. */
  bySubject: { subject: string; masteryPercent: number; quizzesTaken: number }[];
};

const UNPLACED = "Unassigned";

export function groupIntoClasses(rows: StudentInsightRow[]): TeacherClass[] {
  const classes = new Map<string, TeacherClass>();

  for (const row of rows) {
    const sectionName = row.section ?? UNPLACED;
    const key = `${row.grade}::${sectionName}`;
    let entry = classes.get(key);
    if (!entry) {
      entry = {
        id: encodeURIComponent(key),
        sectionName,
        gradeName: row.grade,
        academicPeriod: row.academic_period,
        subjects: [],
        students: [],
      };
      classes.set(key, entry);
    }
    if (!entry.subjects.includes(row.subject)) {
      entry.subjects.push(row.subject);
    }

    let student = entry.students.find((s) => s.id === row.student_id);
    if (!student) {
      student = {
        id: row.student_id,
        fullName: row.full_name,
        identifier: row.student_identifier,
        attendancePercent: row.attendance_percent,
        bySubject: [],
      };
      entry.students.push(student);
    }
    student.bySubject.push({
      subject: row.subject,
      masteryPercent: row.mastery_percent,
      quizzesTaken: row.quizzes_taken,
    });
  }

  for (const entry of classes.values()) {
    entry.subjects.sort();
    entry.students.sort((a, b) => a.fullName.localeCompare(b.fullName));
    for (const student of entry.students) {
      student.bySubject.sort((a, b) => a.subject.localeCompare(b.subject));
    }
  }

  return [...classes.values()].sort(
    (a, b) =>
      a.gradeName.localeCompare(b.gradeName, undefined, { numeric: true }) ||
      a.sectionName.localeCompare(b.sectionName),
  );
}

export type TeacherClassesState = {
  loading: boolean;
  error: string | null;
  classes: TeacherClass[];
  /** The server's own description of the boundary, shown so the teacher knows the extent. */
  scopeDescription: string;
};

export function useTeacherClasses(): TeacherClassesState {
  const [rows, setRows] = useState<StudentInsightRow[]>([]);
  const [scopeDescription, setScopeDescription] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchStudentInsights()
      .then((page) => {
        if (cancelled) return;
        setRows(page.items);
        setScopeDescription(page.scope_description);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Could not load your classes.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const classes = useMemo(() => groupIntoClasses(rows), [rows]);
  return { loading, error, classes, scopeDescription };
}

export function findClass(classes: TeacherClass[], id: string): TeacherClass | undefined {
  return classes.find((entry) => entry.id === id);
}

/** Average across the subjects a student has actually attempted. */
export function averageMastery(student: TeacherClassStudent): number | null {
  const attempted = student.bySubject.filter((s) => s.quizzesTaken > 0);
  if (attempted.length === 0) return null;
  return attempted.reduce((sum, s) => sum + s.masteryPercent, 0) / attempted.length;
}

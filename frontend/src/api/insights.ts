import { apiRequest } from "./client";

/** One row of the master register: a student, in a subject, for a term. */
export type StudentInsightRow = {
  student_id: string;
  full_name: string;
  student_identifier: string;
  grade: string;
  section: string | null;
  subject: string;
  academic_period: string;
  quizzes_taken: number;
  quizzes_passed: number;
  mastery_percent: number;
  lessons_completed: number;
  attendance_percent: number | null;
};

export type StudentInsightPage = {
  /** Plain-English summary of the caller's boundary, e.g. "9 students across 3 assignments". */
  scope_description: string;
  rows_returned: number;
  items: StudentInsightRow[];
};

export type AskAnswer = {
  question: string;
  answered: boolean;
  /** Present when `answered` is false — says what is missing, in plain words. */
  reason: string | null;
  /** The query the model wrote. */
  model_sql: string | null;
  /** What actually ran, with the permission boundary prepended. */
  executed_sql: string | null;
  columns: string[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
};

/**
 * The register, already narrowed to whatever the signed-in person may see.
 *
 * There is no "which teacher" parameter and there must never be one: the server resolves
 * the boundary from the token. An administrator gets the institution, a teacher gets the
 * classes they are assigned to, a student gets themselves.
 */
export async function fetchStudentInsights(params?: {
  subject?: string;
  grade?: string;
  section?: string;
  limit?: number;
}): Promise<StudentInsightPage> {
  const query = new URLSearchParams();
  if (params?.subject) query.set("subject", params.subject);
  if (params?.grade) query.set("grade", params.grade);
  if (params?.section) query.set("section", params.section);
  query.set("limit", String(params?.limit ?? 500));
  return apiRequest<StudentInsightPage>(`/insights/students?${query.toString()}`);
}

/** One subject of one student, as far as the signed-in person is permitted to see it. */
export type SubjectStanding = {
  subject: string;
  quizzes_taken: number;
  quizzes_passed: number;
  mastery_percent: number;
  lessons_started: number;
  lessons_completed: number;
  last_attempt_at: string | null;
};

export type StudentAttempt = {
  attempt_id: string;
  subject: string;
  quiz_title: string;
  attempt_number: number;
  score_percent: number | null;
  passed: boolean | null;
  submitted_at: string | null;
};

/** A day the student was not simply present. Whole-day records, not per subject. */
export type StudentAbsence = {
  on_date: string;
  status: string;
};

export type StudentDetail = {
  student_id: string;
  full_name: string;
  student_identifier: string;
  grade: string;
  section: string | null;
  academic_period: string;
  subjects: SubjectStanding[];
  attempts: StudentAttempt[];
  days_present: number;
  days_counted: number;
  attendance_percent: number | null;
  absences: StudentAbsence[];
};

/**
 * One student's record.
 *
 * A student the caller may not see gives 404 — the same answer as a student who does not
 * exist, deliberately, so the interface cannot tell the two apart either.
 */
export async function fetchStudentDetail(studentId: string): Promise<StudentDetail> {
  return apiRequest<StudentDetail>(`/insights/students/${studentId}`);
}

/** Ask a question in English. The boundary is applied to the generated query server-side. */
export async function askStudents(question: string, limit = 100): Promise<AskAnswer> {
  return apiRequest<AskAnswer>("/ask/students", {
    method: "POST",
    body: { question, limit },
  });
}

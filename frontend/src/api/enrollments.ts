import { apiRequest } from "./client";
import type { EnrollmentSummary } from "./types";

export async function fetchEnrollments(): Promise<EnrollmentSummary> {
  return apiRequest<EnrollmentSummary>("/me/enrollments");
}

export async function enrollPocMath(confirm = true): Promise<EnrollmentSummary> {
  return apiRequest<EnrollmentSummary>("/me/enrollments/poc-math", {
    method: "POST",
    body: { confirm },
  });
}

export function hasActiveSubjectEnrollment(summary: EnrollmentSummary): boolean {
  return summary.subject_enrollments.some((e) => e.status === "active");
}

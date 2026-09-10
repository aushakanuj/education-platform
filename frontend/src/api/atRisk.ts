import { apiRequest } from "./client";

/** One named reason a flag exists -- never empty; see docs/design/08-at-risk-early-warning.md AR-1. */
export type AtRiskDriver = {
  metric: string;
  value: number;
  comparison: string;
  window: string;
};

/**
 * One student's at-risk flag, already narrowed to whatever the signed-in person may see.
 *
 * `subject` is null only for an attendance-only flag -- the student has no single owning
 * subject teacher for it, so it is visible to administrators only (spec Section 7.2). A
 * teacher's response never contains one of these; only an administrator's can.
 */
export type AtRiskFlag = {
  id: string;
  student_id: string;
  student_name: string;
  grade_subject_offering_id: string | null;
  subject: string | null;
  tier: "monitor" | "attention" | "urgent";
  drivers: AtRiskDriver[];
  status: "active" | "dismissed" | "resolved";
  dismissed_by_user_id: string | null;
  dismissal_note: string | null;
};

export type AtRiskFlagList = {
  rows_returned: number;
  items: AtRiskFlag[];
};

/** Active flags the signed-in teacher or administrator may see. Never a student -- that
 * request is refused before it reaches this module (403, not an empty list). */
export async function fetchAtRiskFlags(): Promise<AtRiskFlagList> {
  return apiRequest<AtRiskFlagList>("/at-risk/flags");
}

/**
 * AR-4: dismiss a flag. `note` is optional -- dismissal needs no justification, but the
 * action itself is always audited regardless.
 *
 * The response's `student_name` and `subject` come back blank (the backend does not
 * re-resolve them on dismiss) -- callers should keep the pre-dismiss row's display fields
 * rather than trust this response for them.
 */
export async function dismissAtRiskFlag(flagId: string, note?: string): Promise<AtRiskFlag> {
  return apiRequest<AtRiskFlag>(`/at-risk/flags/${flagId}/dismiss`, {
    method: "POST",
    body: { note: note?.trim() ? note.trim() : null },
  });
}

export type AtRiskRecomputeResult = {
  students_considered: number;
  flags_active: number;
  flags_resolved: number;
};

/** Administrator-only: re-run the engine for the whole institution. A teacher's token gets
 * a 403 here, same as the backend -- there is no narrower "recompute my classes" action. */
export async function recomputeAtRisk(): Promise<AtRiskRecomputeResult> {
  return apiRequest<AtRiskRecomputeResult>("/at-risk/recompute", { method: "POST" });
}

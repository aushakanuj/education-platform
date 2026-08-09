import { describe, expect, it } from "vitest";

import { buildSubmitPayload } from "../api/attempts";
import { hasActiveSubjectEnrollment } from "../api/enrollments";
import type { EnrollmentSummary } from "../api/types";

describe("buildSubmitPayload", () => {
  it("maps question numbers to selected option labels sorted by number", () => {
    const payload = buildSubmitPayload({
      3: "C",
      1: "A",
      2: "B",
    });
    expect(payload).toEqual({
      answers: [
        { question_number: 1, selected_option_label: "A" },
        { question_number: 2, selected_option_label: "B" },
        { question_number: 3, selected_option_label: "C" },
      ],
    });
  });
});

describe("hasActiveSubjectEnrollment", () => {
  it("returns true when an active subject enrollment exists", () => {
    const summary: EnrollmentSummary = {
      grade_enrollments: [],
      subject_enrollments: [
        {
          id: "1",
          grade_subject_offering_id: "2",
          academic_period_id: "3",
          academic_period_name: "2026-27",
          grade_name: "Grade 8",
          subject_id: "4",
          subject_code: "MATH",
          subject_name: "Mathematics",
          status: "active",
        },
      ],
    };
    expect(hasActiveSubjectEnrollment(summary)).toBe(true);
  });

  it("returns false when subject enrollments are inactive or missing", () => {
    const empty: EnrollmentSummary = {
      grade_enrollments: [],
      subject_enrollments: [],
    };
    const inactive: EnrollmentSummary = {
      grade_enrollments: [],
      subject_enrollments: [
        {
          id: "1",
          grade_subject_offering_id: "2",
          academic_period_id: "3",
          academic_period_name: "2026-27",
          grade_name: "Grade 8",
          subject_id: "4",
          subject_code: "MATH",
          subject_name: "Mathematics",
          status: "withdrawn",
        },
      ],
    };
    expect(hasActiveSubjectEnrollment(empty)).toBe(false);
    expect(hasActiveSubjectEnrollment(inactive)).toBe(false);
  });
});

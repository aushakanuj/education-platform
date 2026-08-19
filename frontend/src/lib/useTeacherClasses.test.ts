import { describe, expect, it } from "vitest";

import { averageMastery, groupIntoClasses } from "./useTeacherClasses";
import type { StudentInsightRow } from "../api/insights";

function row(over: Partial<StudentInsightRow>): StudentInsightRow {
  return {
    student_id: "s1",
    full_name: "Aisha Rahman",
    student_identifier: "S-0001",
    grade: "Grade 8",
    section: "8A",
    subject: "Mathematics",
    academic_period: "Term 1 2026",
    quizzes_taken: 5,
    quizzes_passed: 2,
    mastery_percent: 56,
    lessons_completed: 3,
    attendance_percent: 62,
    ...over,
  };
}

describe("groupIntoClasses", () => {
  it("turns the scoped register into one entry per grade and section", () => {
    // What Meera's boundary actually returns: two sections of Maths, one of Science.
    const classes = groupIntoClasses([
      row({ student_id: "a", section: "8A", subject: "Mathematics" }),
      row({ student_id: "b", section: "8B", subject: "Mathematics" }),
      row({ student_id: "c", section: "9A", grade: "Grade 9", subject: "Science" }),
    ]);

    expect(classes.map((c) => `${c.gradeName} ${c.sectionName}`)).toEqual([
      "Grade 8 8A",
      "Grade 8 8B",
      "Grade 9 9A",
    ]);
  });

  it("keeps one student per class however many subjects they have", () => {
    const classes = groupIntoClasses([
      row({ student_id: "a", subject: "Mathematics", mastery_percent: 56 }),
      row({ student_id: "a", subject: "Science", mastery_percent: 72 }),
    ]);

    expect(classes).toHaveLength(1);
    expect(classes[0].students).toHaveLength(1);
    expect(classes[0].students[0].bySubject.map((s) => s.subject)).toEqual([
      "Mathematics",
      "Science",
    ]);
    expect(classes[0].subjects).toEqual(["Mathematics", "Science"]);
  });

  it("never invents a subject the server did not send", () => {
    // The teacher's boundary is applied server-side. If English is absent from the
    // response it is absent from her screen -- the browser must not fill gaps.
    const classes = groupIntoClasses([row({ subject: "Mathematics" })]);
    expect(classes[0].subjects).toEqual(["Mathematics"]);
  });

  it("orders grades numerically so Grade 10 does not sort before Grade 6", () => {
    const classes = groupIntoClasses([
      row({ grade: "Grade 10", section: "10A" }),
      row({ grade: "Grade 6", section: "6A" }),
    ]);
    expect(classes.map((c) => c.gradeName)).toEqual(["Grade 6", "Grade 10"]);
  });

  it("copes with a student who has no section", () => {
    const classes = groupIntoClasses([row({ section: null })]);
    expect(classes[0].sectionName).toBe("Unassigned");
  });
});

describe("averageMastery", () => {
  it("ignores subjects with no attempts, which score zero and would drag it down", () => {
    const [entry] = groupIntoClasses([
      row({ subject: "Mathematics", mastery_percent: 56, quizzes_taken: 5 }),
      row({ subject: "Science", mastery_percent: 0, quizzes_taken: 0 }),
    ]);
    expect(averageMastery(entry.students[0])).toBe(56);
  });

  it("returns null when nothing has been attempted at all", () => {
    const [entry] = groupIntoClasses([row({ mastery_percent: 0, quizzes_taken: 0 })]);
    expect(averageMastery(entry.students[0])).toBeNull();
  });
});

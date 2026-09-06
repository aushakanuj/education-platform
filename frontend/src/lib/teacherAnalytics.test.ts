import { describe, expect, it } from "vitest";

import type { AtRiskFlag } from "../api/atRisk";
import { computeSectionAnalytics, computeSubjectOverview, tierFor } from "./teacherAnalytics";
import type { TeacherClass, TeacherClassStudent } from "./useTeacherClasses";

function student(over: Partial<TeacherClassStudent> = {}): TeacherClassStudent {
  return {
    id: crypto.randomUUID(),
    fullName: "Test Student",
    identifier: "S-0000",
    attendancePercent: 90,
    bySubject: [{ subject: "Mathematics", masteryPercent: 80, quizzesTaken: 3 }],
    ...over,
  };
}

function section(over: Partial<TeacherClass> = {}): TeacherClass {
  return {
    id: "grade-8-8a",
    sectionName: "8A",
    gradeName: "Grade 8",
    academicPeriod: "Term 1 2026",
    subjects: ["Mathematics"],
    students: [student()],
    ...over,
  };
}

function flag(over: Partial<AtRiskFlag> = {}): AtRiskFlag {
  return {
    id: crypto.randomUUID(),
    student_id: "s1",
    student_name: "Aisha Rahman",
    grade_subject_offering_id: "off-1",
    subject: "Mathematics",
    tier: "urgent",
    drivers: [],
    status: "active",
    dismissed_by_user_id: null,
    dismissal_note: null,
    ...over,
  };
}

describe("tierFor", () => {
  it("has no gap and no overlap at the boundaries", () => {
    expect(tierFor(null)).toBe("not_started");
    expect(tierFor(49.9)).toBe("struggling");
    expect(tierFor(50)).toBe("average");
    expect(tierFor(69.9)).toBe("average");
    expect(tierFor(70)).toBe("strong");
  });
});

describe("computeSectionAnalytics", () => {
  it("averages mastery and attendance only across students who have a value", () => {
    const s1 = student({ id: "s1", attendancePercent: 80, bySubject: [
      { subject: "Mathematics", masteryPercent: 60, quizzesTaken: 2 },
    ] });
    const s2 = student({ id: "s2", attendancePercent: null, bySubject: [
      { subject: "Mathematics", masteryPercent: 40, quizzesTaken: 1 },
    ] });
    const [result] = computeSectionAnalytics([section({ students: [s1, s2] })], []);

    expect(result.averageMastery).toBe(50);
    expect(result.averageAttendance).toBe(80);
  });

  it("counts a never-attempted student as not_started, not struggling", () => {
    const neverAttempted = student({ id: "s1", bySubject: [] });
    const [result] = computeSectionAnalytics([section({ students: [neverAttempted] })], []);

    expect(result.distribution).toEqual({
      strong: 0,
      average: 0,
      struggling: 0,
      not_started: 1,
    });
  });

  it("buckets the performance distribution across all four tiers", () => {
    const strong = student({ id: "s1", bySubject: [{ subject: "Mathematics", masteryPercent: 85, quizzesTaken: 2 }] });
    const average_ = student({ id: "s2", bySubject: [{ subject: "Mathematics", masteryPercent: 60, quizzesTaken: 2 }] });
    const struggling = student({ id: "s3", bySubject: [{ subject: "Mathematics", masteryPercent: 30, quizzesTaken: 2 }] });
    const [result] = computeSectionAnalytics(
      [section({ students: [strong, average_, struggling] })],
      [],
    );

    expect(result.distribution).toEqual({ strong: 1, average: 1, struggling: 1, not_started: 0 });
  });

  it("only counts at-risk flags for students actually in this section", () => {
    const s1 = student({ id: "s1" });
    const sections = [
      section({ id: "sec-a", students: [s1] }),
      section({ id: "sec-b", students: [student({ id: "s2" })] }),
    ];
    const flags = [flag({ student_id: "s1", tier: "urgent" })];

    const results = computeSectionAnalytics(sections, flags);
    const secA = results.find((r) => r.sectionId === "sec-a")!;
    const secB = results.find((r) => r.sectionId === "sec-b")!;

    expect(secA.atRiskCounts).toEqual({ urgent: 1, attention: 0, monitor: 0, total: 1 });
    expect(secB.atRiskCounts).toEqual({ urgent: 0, attention: 0, monitor: 0, total: 0 });
  });

  it("flags low attendance students below 75%, sorted lowest first, capped at five", () => {
    const students = [
      student({ id: "s1", fullName: "A", attendancePercent: 74 }),
      student({ id: "s2", fullName: "B", attendancePercent: 60 }),
      student({ id: "s3", fullName: "C", attendancePercent: 90 }),
      student({ id: "s4", fullName: "D", attendancePercent: 50 }),
      student({ id: "s5", fullName: "E", attendancePercent: 65 }),
      student({ id: "s6", fullName: "F", attendancePercent: 70 }),
      student({ id: "s7", fullName: "G", attendancePercent: 40 }),
    ];
    const [result] = computeSectionAnalytics([section({ students })], []);

    expect(result.lowAttendance).toHaveLength(5);
    expect(result.lowAttendance[0]).toEqual({ studentId: "s7", fullName: "G", attendancePercent: 40 });
    expect(result.lowAttendance.map((s) => s.studentId)).not.toContain("s3");
  });

  it("averages each subject only across students who have actually attempted it", () => {
    const s1 = student({ id: "s1", bySubject: [
      { subject: "Mathematics", masteryPercent: 80, quizzesTaken: 2 },
      { subject: "Science", masteryPercent: 0, quizzesTaken: 0 },
    ] });
    const s2 = student({ id: "s2", bySubject: [
      { subject: "Mathematics", masteryPercent: 60, quizzesTaken: 1 },
    ] });
    const [result] = computeSectionAnalytics([section({ students: [s1, s2] })], []);

    expect(result.subjectAverages).toEqual([{ subject: "Mathematics", averageMastery: 70 }]);
  });
});

describe("computeSubjectOverview", () => {
  it("rolls subject averages up across every section, not just one", () => {
    const sections = [
      section({
        id: "sec-a",
        students: [student({ bySubject: [{ subject: "Mathematics", masteryPercent: 80, quizzesTaken: 1 }] })],
      }),
      section({
        id: "sec-b",
        students: [student({ bySubject: [{ subject: "Mathematics", masteryPercent: 60, quizzesTaken: 1 }] })],
      }),
    ];

    expect(computeSubjectOverview(sections)).toEqual([
      { subject: "Mathematics", averageMastery: 70 },
    ]);
  });

  it("sorts weakest subject first, so the thing needing attention is at the top", () => {
    const sections = [
      section({
        students: [
          student({
            bySubject: [
              { subject: "Mathematics", masteryPercent: 40, quizzesTaken: 1 },
              { subject: "English", masteryPercent: 90, quizzesTaken: 1 },
            ],
          }),
        ],
      }),
    ];

    expect(computeSubjectOverview(sections).map((s) => s.subject)).toEqual([
      "Mathematics",
      "English",
    ]);
  });
});

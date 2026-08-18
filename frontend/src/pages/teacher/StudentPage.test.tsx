import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { StudentPage, attemptTrend } from "./StudentPage";
import type { StudentAttempt, StudentDetail } from "../../api/insights";

const fetchStudentDetail = vi.fn();

vi.mock("../../api/insights", () => ({
  fetchStudentDetail: (...args: unknown[]) => fetchStudentDetail(...args),
}));

function attempt(over: Partial<StudentAttempt> = {}): StudentAttempt {
  return {
    attempt_id: crypto.randomUUID(),
    subject: "Mathematics",
    quiz_title: "Fractions mastery check",
    attempt_number: 1,
    score_percent: 70,
    passed: true,
    submitted_at: "2026-08-10T09:00:00Z",
    ...over,
  };
}

function detail(over: Partial<StudentDetail> = {}): StudentDetail {
  return {
    student_id: "abc",
    full_name: "Aisha Rahman",
    student_identifier: "S-0001",
    grade: "Grade 8",
    section: "8A",
    academic_period: "Term 1 2026",
    subjects: [
      {
        subject: "Mathematics",
        quizzes_taken: 6,
        quizzes_passed: 2,
        mastery_percent: 48,
        lessons_started: 5,
        lessons_completed: 3,
        last_attempt_at: "2026-08-10T09:00:00Z",
      },
    ],
    attempts: [attempt()],
    days_present: 40,
    days_counted: 60,
    attendance_percent: 66.7,
    absences: [{ on_date: "2026-08-11", status: "absent" }],
    ...over,
  };
}

function renderStudent() {
  return render(
    <MemoryRouter
      initialEntries={["/teacher/classes/grade-8-8a/students/abc"]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route path="/teacher/classes/:sectionId/students/:studentId" element={<StudentPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("attemptTrend", () => {
  const scores = (values: number[]) => values.map((v) => attempt({ score_percent: v }));

  it("says nothing until three recent quizzes have at least two behind them", () => {
    expect(attemptTrend(scores([30, 40, 50, 90]))).toBeNull();
  });

  it("ignores a move small enough to be ordinary variation", () => {
    // Newest first: 70,70,70 against 72,72 — a 2 point drift, not a direction.
    expect(attemptTrend(scores([70, 70, 70, 72, 72]))).toBeNull();
  });

  it("reports a fall, comparing the recent three against everything before them", () => {
    const trend = attemptTrend(scores([40, 45, 50, 80, 85, 90]));
    expect(trend?.direction).toBe("down");
    expect(Math.round(trend?.recent ?? 0)).toBe(45);
    expect(Math.round(trend?.earlier ?? 0)).toBe(85);
    expect(trend?.recentCount).toBe(3);
    expect(trend?.earlierCount).toBe(3);
  });

  it("compares against an uneven earlier group, and reports how uneven", () => {
    // Aisha's shape in the demo data: five quizzes, sliding.
    const trend = attemptTrend(scores([38, 47, 56, 65, 74]));
    expect(trend?.direction).toBe("down");
    expect(trend?.recentCount).toBe(3);
    expect(trend?.earlierCount).toBe(2);
    expect(Math.round(trend?.earlier ?? 0)).toBe(70);
  });

  it("reports a rise the same way", () => {
    expect(attemptTrend(scores([90, 85, 80, 45, 40]))?.direction).toBe("up");
  });

  it("skips attempts that were never marked rather than scoring them zero", () => {
    const withUnmarked = [
      ...scores([40, 45, 50]),
      attempt({ score_percent: null }),
      ...scores([80, 85]),
    ];
    const trend = attemptTrend(withUnmarked);
    expect(trend?.direction).toBe("down");
    expect(trend?.earlierCount).toBe(2);
  });
});

describe("StudentPage", () => {
  beforeEach(() => {
    fetchStudentDetail.mockReset();
    fetchStudentDetail.mockResolvedValue(detail());
  });

  it("names the student and their class", async () => {
    renderStudent();
    expect(await screen.findByRole("heading", { level: 1, name: "Aisha Rahman" })).toBeInTheDocument();
    expect(screen.getByText(/S-0001 · Grade 8 · 8A/)).toBeInTheDocument();
  });

  it("flags attendance below the exam-eligibility threshold", async () => {
    renderStudent();
    expect(await screen.findByText("67%")).toBeInTheDocument();
    expect(screen.getByText(/Below the 75%/)).toBeInTheDocument();
  });

  it("shows only the subjects the server returned, and says so", async () => {
    renderStudent();
    expect(await screen.findByRole("heading", { level: 3, name: "Mathematics" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 3, name: "English" })).not.toBeInTheDocument();
    expect(screen.getByText(/not shown here/)).toBeInTheDocument();
  });

  it("lists the quiz history with its result", async () => {
    renderStudent();
    const table = await screen.findByRole("table");
    const row = within(table).getAllByRole("row")[1];
    expect(within(row).getByText("Fractions mastery check")).toBeInTheDocument();
    expect(within(row).getByText("70%")).toBeInTheDocument();
    expect(within(row).getByText("Passed")).toBeInTheDocument();
  });

  it("says plainly when nothing has been submitted", async () => {
    fetchStudentDetail.mockResolvedValue(detail({ attempts: [] }));
    renderStudent();
    expect(await screen.findByText(/Nothing submitted yet/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows the refusal as a message, not a blank page", async () => {
    fetchStudentDetail.mockRejectedValue(new Error("No such student"));
    renderStudent();
    expect(await screen.findByRole("alert")).toHaveTextContent("No such student");
  });
});

import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { StudentPage } from "./StudentPage";
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

  it("points to the real at-risk engine rather than guessing a trend itself", async () => {
    renderStudent();
    const link = await screen.findByRole("link", { name: /See at-risk flags/ });
    expect(link).toHaveAttribute("href", "/teacher/at-risk");
  });
});

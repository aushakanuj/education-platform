import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ClassesPage } from "./ClassesPage";
import { RosterPage } from "./RosterPage";
import { SectionPage } from "./SectionPage";
import type { StudentInsightPage } from "../../api/insights";

const fetchStudentInsights = vi.fn();

vi.mock("../../api/insights", () => ({
  fetchStudentInsights: (...args: unknown[]) => fetchStudentInsights(...args),
}));

function studentRow(over: Partial<StudentInsightPage["items"][number]>) {
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

/** The real route tree, so a link that does not resolve fails the test. */
function renderApp(initialPath = "/teacher") {
  return render(
    <MemoryRouter
      initialEntries={[initialPath]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route path="/teacher" element={<ClassesPage />} />
        <Route path="/teacher/classes/:sectionId" element={<SectionPage />} />
        <Route path="/teacher/classes/:sectionId/students" element={<RosterPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("navigating from a class to its students", () => {
  beforeEach(() => {
    fetchStudentInsights.mockReset();
    fetchStudentInsights.mockResolvedValue({
      scope_description: "2 students across 1 assignment",
      rows_returned: 2,
      items: [
        studentRow({ student_id: "a", full_name: "Aisha Rahman", attendance_percent: 62 }),
        studentRow({ student_id: "b", full_name: "Hassan Nair", attendance_percent: 91 }),
      ],
    });
  });

  it("opens the class instead of bouncing back to the list", async () => {
    // Regression: the link was percent-encoded but react-router hands the param back
    // decoded, so nothing matched and SectionPage redirected straight to /teacher.
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("link", { name: /Grade 8 · 8A/ }));

    expect(await screen.findByRole("heading", { level: 1, name: "Grade 8 · 8A" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Student roster/ })).toBeInTheDocument();
  });

  it("reaches the roster and lists the students", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("link", { name: /Grade 8 · 8A/ }));
    await user.click(await screen.findByRole("link", { name: /Student roster/ }));

    expect(await screen.findByText("Aisha Rahman")).toBeInTheDocument();
    expect(screen.getByText("Hassan Nair")).toBeInTheDocument();
  });

  it("flags attendance below the eligibility threshold", async () => {
    const user = userEvent.setup();
    renderApp("/teacher/classes/grade-8-8a/students");

    expect(await screen.findByText("Aisha Rahman")).toBeInTheDocument();
    expect(screen.getByText("62%")).toBeInTheDocument();
    expect(screen.getByText("91%")).toBeInTheDocument();
    void user;
  });

  it("still redirects when the class genuinely does not exist", async () => {
    renderApp("/teacher/classes/grade-99-zz");
    expect(await screen.findByRole("heading", { level: 1, name: "My classes" })).toBeInTheDocument();
  });
});

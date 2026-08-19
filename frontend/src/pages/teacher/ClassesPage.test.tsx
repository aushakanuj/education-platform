import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ClassesPage } from "./ClassesPage";
import type { StudentInsightPage } from "../../api/insights";

const fetchStudentInsights = vi.fn();

vi.mock("../../api/insights", () => ({
  fetchStudentInsights: (...args: unknown[]) => fetchStudentInsights(...args),
}));

function page(items: StudentInsightPage["items"], description: string): StudentInsightPage {
  return { scope_description: description, rows_returned: items.length, items };
}

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

function renderPage() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ClassesPage />
    </MemoryRouter>,
  );
}

describe("ClassesPage", () => {
  beforeEach(() => {
    fetchStudentInsights.mockReset();
  });

  it("shows the classes the server returned, and nothing else", async () => {
    fetchStudentInsights.mockResolvedValue(
      page(
        [
          studentRow({ student_id: "a", section: "8A" }),
          studentRow({ student_id: "b", section: "8B" }),
        ],
        "6 students across 2 assignments",
      ),
    );

    renderPage();

    expect(await screen.findByRole("link", { name: /Grade 8 · 8A/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Grade 8 · 8B/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "My classes" })).toBeInTheDocument();
  });

  it("shows the server's description of the boundary rather than inventing one", async () => {
    fetchStudentInsights.mockResolvedValue(
      page([studentRow({})], "9 students across 3 assignments"),
    );
    renderPage();
    expect(await screen.findByText(/9 students across 3 assignments/i)).toBeInTheDocument();
  });

  it("explains an empty result instead of showing a blank page", async () => {
    fetchStudentInsights.mockResolvedValue(page([], "No students in scope"));
    renderPage();
    expect(await screen.findByText(/no teaching assignments/i)).toBeInTheDocument();
  });

  it("surfaces a failure rather than pretending there are no classes", async () => {
    fetchStudentInsights.mockRejectedValue(new Error("Request failed (500)"));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("Request failed (500)");
  });
});

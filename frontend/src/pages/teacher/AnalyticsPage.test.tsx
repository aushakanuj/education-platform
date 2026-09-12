import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AnalyticsPage } from "./AnalyticsPage";
import type { StudentInsightPage } from "../../api/insights";
import type { AtRiskFlag } from "../../api/atRisk";

vi.mock("../../api/insights", () => ({
  fetchStudentInsights: vi.fn(),
}));
vi.mock("../../api/atRisk", () => ({
  fetchAtRiskFlags: vi.fn(),
}));

import { fetchStudentInsights } from "../../api/insights";
import { fetchAtRiskFlags } from "../../api/atRisk";

function row(over: Partial<StudentInsightPage["items"][number]> = {}) {
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

function flag(over: Partial<AtRiskFlag> = {}): AtRiskFlag {
  return {
    id: "flag-1",
    student_id: "s1",
    student_name: "Aisha Rahman",
    grade_subject_offering_id: "gso-1",
    subject: "Mathematics",
    tier: "urgent",
    drivers: [],
    status: "active",
    dismissed_by_user_id: null,
    dismissal_note: null,
    ...over,
  };
}

function renderPage() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AnalyticsPage />
    </MemoryRouter>,
  );
}

describe("AnalyticsPage", () => {
  beforeEach(() => {
    vi.mocked(fetchStudentInsights).mockReset();
    vi.mocked(fetchAtRiskFlags).mockReset();
    vi.mocked(fetchAtRiskFlags).mockResolvedValue({ rows_returned: 0, items: [] });
  });

  it("summarises students, sections, and averages across the teacher's classes", async () => {
    vi.mocked(fetchStudentInsights).mockResolvedValue({
      scope_description: "2 students across 1 assignment",
      rows_returned: 2,
      items: [
        row({ student_id: "a", full_name: "Aisha Rahman", mastery_percent: 80, attendance_percent: 90 }),
        row({ student_id: "b", full_name: "Hassan Nair", mastery_percent: 60, attendance_percent: 70 }),
      ],
    });
    renderPage();

    expect(await screen.findByRole("heading", { level: 1, name: "Class analytics" })).toBeInTheDocument();
    await screen.findByText("Students");

    const studentsCard = screen.getByText("Students").closest<HTMLElement>(".card")!;
    expect(within(studentsCard).getByText("2")).toBeInTheDocument();

    const masteryCard = screen.getByText("Average mastery").closest<HTMLElement>(".card")!;
    expect(within(masteryCard).getByText("70%")).toBeInTheDocument(); // (80+60)/2
  });

  it("groups by section and shows one panel per class", async () => {
    vi.mocked(fetchStudentInsights).mockResolvedValue({
      scope_description: "3 students across 2 assignments",
      rows_returned: 3,
      items: [
        row({ student_id: "a", grade: "Grade 8", section: "8A" }),
        row({ student_id: "b", grade: "Grade 9", section: "9B", subject: "Science" }),
      ],
    });
    renderPage();

    expect(await screen.findByRole("heading", { level: 2, name: "Grade 8 · 8A" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Grade 9 · 9B" })).toBeInTheDocument();
  });

  it("flags students below 75% attendance in the low-attendance list", async () => {
    vi.mocked(fetchStudentInsights).mockResolvedValue({
      scope_description: "1 student across 1 assignment",
      rows_returned: 1,
      items: [row({ full_name: "Aisha Rahman", attendance_percent: 62 })],
    });
    renderPage();

    expect(await screen.findByText("Aisha Rahman")).toBeInTheDocument();
    expect(screen.getByText("Below 75% attendance")).toBeInTheDocument();
  });

  it("surfaces active at-risk counts per section with a link to the full list", async () => {
    vi.mocked(fetchStudentInsights).mockResolvedValue({
      scope_description: "1 student across 1 assignment",
      rows_returned: 1,
      items: [row({ student_id: "s1" })],
    });
    vi.mocked(fetchAtRiskFlags).mockResolvedValue({
      rows_returned: 1,
      items: [flag({ student_id: "s1", tier: "urgent" })],
    });
    renderPage();

    expect(await screen.findByText("1 urgent")).toBeInTheDocument();
    const link = screen.getAllByRole("link", { name: /See at-risk flags/ })[0];
    expect(link).toHaveAttribute("href", "/teacher/at-risk");
  });

  it("says so plainly when the teacher has no assignments yet", async () => {
    vi.mocked(fetchStudentInsights).mockResolvedValue({
      scope_description: "No students in scope",
      rows_returned: 0,
      items: [],
    });
    renderPage();

    expect(await screen.findByText(/no teaching assignments/)).toBeInTheDocument();
  });

  it("shows the server's error rather than a blank page", async () => {
    vi.mocked(fetchStudentInsights).mockRejectedValue(new Error("Session expired."));
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("Session expired.");
  });

  it("reveals the named students behind a tier only after clicking it, with the rule stated", async () => {
    vi.mocked(fetchStudentInsights).mockResolvedValue({
      scope_description: "1 student across 1 assignment",
      rows_returned: 1,
      items: [row({ full_name: "Aisha Rahman", mastery_percent: 80, attendance_percent: 95 })],
    });
    renderPage();

    await screen.findByText("1 strong");
    expect(screen.queryByText("Aisha Rahman")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /1 strong/ }));

    expect(await screen.findByText("Aisha Rahman")).toBeInTheDocument();
    expect(screen.getByText(/Averaging 70% or higher/)).toBeInTheDocument();
  });

  it("plots every class and subject in the heatmap, with a merged row per shared grade", async () => {
    vi.mocked(fetchStudentInsights).mockResolvedValue({
      scope_description: "2 students across 2 assignments",
      rows_returned: 2,
      items: [
        row({ student_id: "a", grade: "Grade 8", section: "8A", mastery_percent: 80 }),
        row({ student_id: "b", grade: "Grade 8", section: "8B", mastery_percent: 60 }),
      ],
    });
    renderPage();

    expect(await screen.findByText("Where to look first")).toBeInTheDocument();

    const grid = screen.getByRole("table");
    expect(within(grid).getByRole("columnheader", { name: "Mathematics" })).toBeInTheDocument();
    expect(within(grid).getByRole("rowheader", { name: /Grade 8 · all sections/ })).toBeInTheDocument();
    // One class each way, so the grade row carries their mean.
    expect(within(grid).getAllByText("70").length).toBeGreaterThan(0);
  });

  it("links each student square to that student", async () => {
    vi.mocked(fetchStudentInsights).mockResolvedValue({
      scope_description: "1 student across 1 assignment",
      rows_returned: 1,
      items: [row({ student_id: "s1", full_name: "Aisha Rahman", grade: "Grade 8", section: "8A" })],
    });
    renderPage();

    const square = await screen.findByRole("link", { name: /Aisha Rahman — 56% mastery/ });
    expect(square).toHaveAttribute("href", "/teacher/classes/grade-8-8a/students/s1");
  });
});

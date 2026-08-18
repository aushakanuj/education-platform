import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RosterPage } from "./RosterPage";
import type { StudentInsightPage } from "../../api/insights";

const fetchStudentInsights = vi.fn();

vi.mock("../../api/insights", () => ({
  fetchStudentInsights: (...args: unknown[]) => fetchStudentInsights(...args),
}));

function row(over: Partial<StudentInsightPage["items"][number]>) {
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

function renderRoster() {
  return render(
    <MemoryRouter
      initialEntries={["/teacher/classes/grade-8-8a/students"]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route path="/teacher/classes/:sectionId/students" element={<RosterPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function names(): string[] {
  return screen
    .getAllByRole("row")
    .slice(1) // drop the header row
    .map((r) => within(r).getAllByRole("cell")[1].textContent ?? "");
}

describe("RosterPage", () => {
  beforeEach(() => {
    fetchStudentInsights.mockReset();
    fetchStudentInsights.mockResolvedValue({
      scope_description: "3 students across 1 assignment",
      rows_returned: 3,
      items: [
        row({ student_id: "a", full_name: "Aisha Rahman", student_identifier: "S-0001",
              mastery_percent: 56, attendance_percent: 62 }),
        row({ student_id: "b", full_name: "Hassan Nair", student_identifier: "S-0002",
              mastery_percent: 88, attendance_percent: 95 }),
        row({ student_id: "c", full_name: "Zaid Iqbal", student_identifier: "S-0003",
              mastery_percent: 71, attendance_percent: 80 }),
      ],
    });
  });

  it("lists everyone, alphabetically by default", async () => {
    renderRoster();
    expect(await screen.findByText("Aisha Rahman")).toBeInTheDocument();
    expect(names().map((n) => n.split("Mathematics")[0].trim())).toEqual([
      "Aisha Rahman",
      "Hassan Nair",
      "Zaid Iqbal",
    ]);
  });

  it("counts the students in the heading so a short list is not mistaken for a bug", async () => {
    renderRoster();
    expect(await screen.findByRole("heading", { level: 1, name: "3 students" })).toBeInTheDocument();
  });

  it("sorts the weakest to the top when asked", async () => {
    const user = userEvent.setup();
    renderRoster();
    await screen.findByText("Aisha Rahman");

    await user.click(screen.getByRole("button", { name: "Lowest attendance" }));

    expect(names()[0]).toContain("Aisha Rahman");
  });

  it("finds a student by name or roll number", async () => {
    const user = userEvent.setup();
    renderRoster();
    await screen.findByText("Aisha Rahman");

    await user.type(screen.getByLabelText("Find a student"), "S-0002");

    const listed = names();
    expect(listed).toHaveLength(1);
    expect(listed[0]).toContain("Hassan Nair");
  });

  it("says so plainly when a search matches nobody", async () => {
    const user = userEvent.setup();
    renderRoster();
    await screen.findByText("Aisha Rahman");

    await user.type(screen.getByLabelText("Find a student"), "Nobody");

    expect(screen.getByText(/No student matches/)).toBeInTheDocument();
  });

  it("makes every name a way into that student's record", async () => {
    renderRoster();
    const link = await screen.findByRole("link", { name: "Aisha Rahman" });
    expect(link).toHaveAttribute("href", "/teacher/classes/grade-8-8a/students/a");
  });

  it("summarises who needs a look, using the early-warning thresholds", async () => {
    renderRoster();
    // Aisha alone is below both 75% attendance and 60% mastery.
    const banner = await screen.findByText(/Worth a look/);
    expect(banner.parentElement).toHaveTextContent("1 below 75% attendance");
    expect(banner.parentElement).toHaveTextContent("1 below 60% mastery");
  });
});

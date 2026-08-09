import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { HomePage } from "./HomePage";

vi.mock("../components/AppShell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock("../api/materials", () => ({
  fetchLearningDirectory: vi.fn(),
}));

import { fetchLearningDirectory } from "../api/materials";

const mockDirectory = {
  subjects: [
    {
      id: "math-1",
      code: "MATH",
      name: "Mathematics",
      grade_name: "Grade 8",
      academic_period_name: "2026-27",
      progress_percent: 0,
      topics: [
        {
          id: "topic-1",
          title: "Approved Materials",
          slug: "approved_materials",
          sequence: 1,
          progress_percent: 0,
          complete: false,
          objectives: [],
          subtopics: [],
          overall_quiz: null,
        },
      ],
    },
  ],
};

describe("HomePage", () => {
  beforeEach(() => {
    vi.mocked(fetchLearningDirectory).mockResolvedValue(mockDirectory as never);
  });

  it("renders mock subjects dashboard without stage workflow chrome", async () => {
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <HomePage />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Your subjects" })).toBeInTheDocument();
    expect(screen.getByText("Student dashboard · demo data")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Mathematics" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Science" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "English" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Social Studies" })).toBeInTheDocument();
    expect(screen.queryByText(/1\.0 Enroll/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Topics$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/You’re in/)).not.toBeInTheDocument();
  });
});

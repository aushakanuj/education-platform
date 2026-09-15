import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { LearningDirectory } from "../../api/types";
import { AdminMaterialsGradesPage } from "./AdminMaterialsGradesPage";

const authState = vi.hoisted(() => ({
  isDevMockSession: false,
}));

vi.mock("../../auth/AuthContext", () => ({
  useAuth: () => ({
    isDevMockSession: authState.isDevMockSession,
  }),
}));

vi.mock("../../api/materials", () => ({
  fetchLearningDirectory: vi.fn(),
}));

import { fetchLearningDirectory } from "../../api/materials";

const mockDirectory: LearningDirectory = {
  subjects: [
    {
      id: "subj-math-uuid",
      code: "MATH",
      name: "Mathematics",
      grade_name: "Grade 8",
      academic_period_name: "2025-2026",
      progress_percent: 0,
      topics: [
        {
          id: "topic-1-uuid",
          title: "Numbers",
          slug: "numbers",
          sequence: 1,
          progress_percent: 0,
          complete: false,
          objectives: [],
          subtopics: [
            {
              id: "st-1-uuid",
              title: "Place value",
              slug: "place-value",
              sequence: 1,
              has_lesson: true,
              lesson_completed: false,
              progress_percent: 0,
              quiz: null,
            },
          ],
          overall_quiz: null,
        },
      ],
    },
  ],
};

describe("AdminMaterialsGradesPage", () => {
  beforeEach(() => {
    authState.isDevMockSession = false;
    vi.mocked(fetchLearningDirectory).mockReset();
    vi.mocked(fetchLearningDirectory).mockResolvedValue(mockDirectory);
  });

  it("smoke-renders grade materials grid from live directory", async () => {
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AdminMaterialsGradesPage />
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { level: 1, name: "Materials" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Upload" })).not.toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByRole("list")).toBeInTheDocument();
    });

    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 2, name: "8" })).toBeInTheDocument();
    expect(screen.getByText(/1 subjects · 1 published topics/i)).toBeInTheDocument();
    expect(screen.getByRole("listitem")).toHaveAttribute(
      "href",
      "/admin/materials/grades/grade-8",
    );
    expect(screen.queryByRole("heading", { level: 2, name: "1" })).not.toBeInTheDocument();
    expect(screen.queryByText(/draft/i)).not.toBeInTheDocument();
    expect(fetchLearningDirectory).toHaveBeenCalled();
  });

  it("does not show the index-only curriculum ingest panel", async () => {
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AdminMaterialsGradesPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByRole("list")).toBeInTheDocument();
    });
    expect(screen.queryByLabelText(/subtopic/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/pdf file/i)).not.toBeInTheDocument();
  });

  it("shows a clear error for fixture mock sessions without JWT", async () => {
    authState.isDevMockSession = true;

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AdminMaterialsGradesPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/real admin JWT/i);
    });
    expect(fetchLearningDirectory).not.toHaveBeenCalled();
  });
});

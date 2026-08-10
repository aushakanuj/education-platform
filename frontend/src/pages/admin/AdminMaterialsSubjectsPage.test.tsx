import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { LearningDirectory } from "../../api/types";
import { AdminMaterialsSubjectsPage } from "./AdminMaterialsSubjectsPage";

vi.mock("../../auth/AuthContext", () => ({
  useAuth: () => ({
    isDevMockSession: false,
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
          subtopics: [],
          overall_quiz: null,
        },
      ],
    },
  ],
};

describe("AdminMaterialsSubjectsPage", () => {
  beforeEach(() => {
    vi.mocked(fetchLearningDirectory).mockReset();
    vi.mocked(fetchLearningDirectory).mockResolvedValue(mockDirectory);
  });

  it("lists live subjects for grade-8 (not fixture grades 1–10)", async () => {
    render(
      <MemoryRouter
        initialEntries={["/admin/materials/grades/grade-8"]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route
            path="/admin/materials/grades/:gradeKey"
            element={<AdminMaterialsSubjectsPage />}
          />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 2, name: "Mathematics" })).toBeInTheDocument();
    });

    expect(screen.getByText("MATH")).toBeInTheDocument();
    expect(screen.getByText("1 published")).toBeInTheDocument();
    expect(screen.queryByText(/draft/i)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Mathematics/i })).toHaveAttribute(
      "href",
      "/admin/materials/grades/grade-8/subjects/subj-math-uuid",
    );
    expect(fetchLearningDirectory).toHaveBeenCalled();
  });
});

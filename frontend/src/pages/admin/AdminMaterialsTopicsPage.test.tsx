import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { LearningDirectory } from "../../api/types";
import { AdminMaterialsTopicsPage } from "./AdminMaterialsTopicsPage";

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

describe("AdminMaterialsTopicsPage", () => {
  beforeEach(() => {
    vi.mocked(fetchLearningDirectory).mockReset();
    vi.mocked(fetchLearningDirectory).mockResolvedValue(mockDirectory);
  });

  it("lists published units from live directory for grade-8 subject", async () => {
    render(
      <MemoryRouter
        initialEntries={["/admin/materials/grades/grade-8/subjects/subj-math-uuid"]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route
            path="/admin/materials/grades/:gradeKey/subjects/:subjectId"
            element={<AdminMaterialsTopicsPage />}
          />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Unit 1: Numbers")).toBeInTheDocument();
    });

    expect(screen.getByText("1 subtopics")).toBeInTheDocument();
    expect(screen.getByText("published")).toBeInTheDocument();
    expect(screen.queryByText(/draft/i)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Unit 1: Numbers/i })).toHaveAttribute(
      "href",
      "/admin/materials/grades/grade-8/subjects/subj-math-uuid/topics/topic-1-uuid",
    );
    expect(fetchLearningDirectory).toHaveBeenCalled();
  });
});

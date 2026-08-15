import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { StartAttemptResponse } from "../api/types";
import { QuizPage } from "./QuizPage";

const startAttempt = vi.fn();
const fetchLearningDirectory = vi.fn();

vi.mock("../api/attempts", () => ({
  startAttempt: (...args: unknown[]) => startAttempt(...args),
  submitAttempt: vi.fn(),
  buildSubmitPayload: vi.fn(),
}));

vi.mock("../api/materials", () => ({
  fetchLearningDirectory: (...args: unknown[]) => fetchLearningDirectory(...args),
}));

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({
    user: { full_name: "Asha Student" },
    enrollments: {
      grade_enrollments: [{ status: "active", grade_name: "Grade 8" }],
      subject_enrollments: [{ status: "active", subject_name: "Mathematics" }],
    },
    enrolled: true,
    signOut: vi.fn(),
  }),
}));

const attempt: StartAttemptResponse = {
  id: "att-1",
  quiz_id: "quiz-1",
  quiz_version_id: "qv-1",
  attempt_number: 1,
  status: "in_progress",
  started_at: null,
  deadline_at: null,
  pass_threshold_percent: 70,
  result_release_mode: "immediate",
  title: "Properties of Rectangles and Squares Quiz",
  scope: "subtopic_mastery",
  target_id: "st-1",
  questions: [
    {
      number: 1,
      difficulty: null,
      prompt: "What is a square?",
      options: [
        { label: "A", text: "A rectangle with equal sides" },
        { label: "B", text: "A circle" },
      ],
    },
  ],
};

describe("QuizPage", () => {
  beforeEach(() => {
    startAttempt.mockReset();
    fetchLearningDirectory.mockReset();
    startAttempt.mockResolvedValue(attempt);
    fetchLearningDirectory.mockResolvedValue({
      subjects: [
        {
          id: "subj-1",
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
              overall_quiz: null,
              subtopics: [
                {
                  id: "st-1",
                  title: "Properties of Rectangles and Squares",
                  slug: "rectangles_squares_properties",
                  sequence: 1,
                  has_lesson: true,
                  lesson_completed: true,
                  progress_percent: 50,
                  quiz: null,
                },
              ],
            },
          ],
        },
      ],
    });
  });

  it("auto-starts the attempt and shows question options", async () => {
    render(
      <MemoryRouter
        initialEntries={["/quizzes/quiz-1"]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/quizzes/:quizId" element={<QuizPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("What is a square?")).toBeInTheDocument();
    expect(startAttempt).toHaveBeenCalledWith("quiz-1");
    expect(screen.queryByText("Ready to begin?")).not.toBeInTheDocument();
    expect(screen.getByText("A rectangle with equal sides")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Back to quiz/i })).toHaveAttribute(
      "href",
      "/subjects/subj-1/subtopics/st-1/lesson",
    );
  });
});

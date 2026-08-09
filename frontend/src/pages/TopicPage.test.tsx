import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { TopicPage } from "./TopicPage";

vi.mock("../api/materials", () => ({
  fetchLearningDirectory: vi.fn(async () => ({
    subjects: [
      {
        id: "subj-1",
        code: "MATH",
        name: "Mathematics",
        grade_name: "Grade 8",
        academic_period_name: "2026-27",
        progress_percent: 25,
        topics: [
          {
            id: "topic-1",
            title: "Approved Materials",
            slug: "approved_materials",
            sequence: 1,
            progress_percent: 25,
            complete: false,
            objectives: [
              "Define rectangles and squares based on their interior angles and side lengths.",
              "Define square numbers and identify perfect squares of natural numbers.",
            ],
            overall_quiz: {
              id: "overall-1",
              title: "Overall",
              scope: "topic_mastery",
              available: true,
              unlocked: false,
              locked_reason: "Pass all subtopic quizzes first",
              pass_threshold_percent: 70,
              attempt_count: 0,
              best_score_percent: null,
              passed: false,
              in_progress_attempt_id: null,
              recent_attempts: [],
            },
            subtopics: [
              {
                id: "st-1",
                title: "Properties of Rectangles and Squares",
                slug: "rectangles_squares_properties",
                sequence: 1,
                has_lesson: true,
                lesson_completed: false,
                progress_percent: 25,
                progress: {
                  status: "opened",
                  opened_at: "2026-08-09T21:00:00Z",
                  last_opened_at: "2026-08-09T21:00:00Z",
                  completed_at: null,
                  last_unit_ordinal: 4,
                  source_material_version_id: "ver-1",
                },
                quiz: {
                  id: "quiz-1",
                  title: "Quiz",
                  scope: "subtopic_mastery",
                  available: true,
                  unlocked: false,
                  locked_reason: "Complete the lesson first",
                  pass_threshold_percent: 70,
                  attempt_count: 0,
                  best_score_percent: null,
                  passed: false,
                  in_progress_attempt_id: null,
                  recent_attempts: [],
                },
              },
            ],
          },
        ],
      },
    ],
  })),
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

describe("TopicPage", () => {
  it("renders hierarchy locks from the learning directory", async () => {
    render(
      <MemoryRouter
        initialEntries={["/subjects/subj-1/topics/topic-1"]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/subjects/:subjectId/topics/:topicId" element={<TopicPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Approved Materials" })).toBeInTheDocument();
    expect(screen.getByText("Objectives")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Define rectangles and squares based on their interior angles and side lengths.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Properties of Rectangles and Squares")).toBeInTheDocument();
    expect(screen.getAllByText("In progress").length).toBeGreaterThan(0);

    const summary = screen.getByText("Properties of Rectangles and Squares").closest("summary");
    expect(summary).toBeTruthy();
    fireEvent.click(summary!);

    expect(screen.getByText("Continue lesson")).toBeInTheDocument();
    expect(screen.getByText("Lesson")).toBeInTheDocument();
    expect(screen.getByText("Quiz")).toBeInTheDocument();
    expect(screen.getByText("Overall topic quiz")).toBeInTheDocument();
    expect(screen.getAllByText(/Locked until/).length).toBeGreaterThan(0);
  });
});

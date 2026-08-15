import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { clearSubtopicLessonCache } from "../lib/useSubtopicLesson";
import { LessonPage } from "./LessonPage";
import { LessonSlidesPage } from "./LessonSlidesPage";
import { QuizHistoryPage } from "./QuizHistoryPage";

const lessonPayload = {
  id: "mat-1",
  title: "Properties of Rectangles and Squares",
  markdown: "",
  source_material_version_id: "ver-1",
  quiz_unlocked: true,
  quiz_id: "quiz-1",
  progress: {
    status: "opened" as const,
    opened_at: "2026-08-09T21:00:00Z",
    last_opened_at: "2026-08-09T21:00:00Z",
    completed_at: null,
    last_unit_ordinal: 2,
    source_material_version_id: "ver-1",
  },
  slides: [
    { number: 1, title: "Introduction", content: "Intro content." },
    { number: 2, title: "Rectangles", content: "Rectangle content." },
    { number: 3, title: "Lesson Summary", content: "- **Rectangle Definition:** Four right angles." },
  ],
};

const recentAttempts = [
  {
    id: "att-2",
    attempt_number: 2,
    status: "submitted",
    score_percent: 50,
    passed: false,
    started_at: "2026-08-09T20:00:00Z",
    submitted_at: "2026-08-09T20:10:00Z",
  },
  {
    id: "att-1",
    attempt_number: 1,
    status: "submitted",
    score_percent: 40,
    passed: false,
    started_at: "2026-08-08T20:00:00Z",
    submitted_at: "2026-08-08T20:10:00Z",
  },
];

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
            objectives: [],
            overall_quiz: null,
            subtopics: [
              {
                id: "st-1",
                title: "Properties of Rectangles and Squares",
                slug: "rectangles_squares_properties",
                sequence: 1,
                has_lesson: true,
                lesson_completed: false,
                progress_percent: 50,
                progress: lessonPayload.progress,
                quiz: {
                  id: "quiz-1",
                  title: "Quiz",
                  scope: "subtopic_mastery",
                  available: true,
                  unlocked: true,
                  locked_reason: null,
                  pass_threshold_percent: 70,
                  attempt_count: 2,
                  best_score_percent: 50,
                  passed: false,
                  in_progress_attempt_id: null,
                  recent_attempts: recentAttempts,
                },
              },
            ],
          },
        ],
      },
    ],
  })),
  getSubtopicMaterial: vi.fn(async () => lessonPayload),
  updateMaterialProgress: vi.fn(async () => lessonPayload.progress),
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

function renderLesson(path = "/subjects/subj-1/subtopics/st-1/lesson") {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route
          path="/subjects/:subjectId/subtopics/:subtopicId/lesson"
          element={<LessonPage />}
        />
        <Route
          path="/subjects/:subjectId/subtopics/:subtopicId/lesson/slides"
          element={<LessonSlidesPage />}
        />
        <Route
          path="/subjects/:subjectId/subtopics/:subtopicId/lesson/history"
          element={<QuizHistoryPage />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("LessonPage", () => {
  beforeEach(() => {
    clearSubtopicLessonCache();
  });

  it("shows equal lesson and quiz panes on the overview", async () => {
    renderLesson();

    expect(await screen.findByRole("heading", { name: "Lesson Summary" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Back to units/i })).toHaveAttribute(
      "href",
      "/subjects/subj-1",
    );
    expect(screen.getByText(/Rectangle Definition/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Last slide" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Continue" })).toHaveAttribute(
      "href",
      "/subjects/subj-1/subtopics/st-1/lesson/slides",
    );
    expect(screen.getByRole("heading", { name: "Last attempt" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Show full history/i })).toHaveAttribute(
      "href",
      "/subjects/subj-1/subtopics/st-1/lesson/history",
    );
    expect(screen.getByRole("link", { name: "Retake quiz" })).toHaveAttribute("href", "/quizzes/quiz-1");
    expect(screen.queryByRole("button", { name: "Next slide" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Performance over time" })).not.toBeInTheDocument();
  });

  it("opens a dedicated slides page when continuing the lesson", async () => {
    const user = userEvent.setup();
    renderLesson();

    await screen.findByRole("heading", { name: "Lesson Summary" });
    await user.click(screen.getByRole("link", { name: "Continue" }));

    expect(screen.queryByText("Loading lesson…")).not.toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Next slide" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Rectangles" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Back to lesson overview/i })).toHaveAttribute(
      "href",
      "/subjects/subj-1/subtopics/st-1/lesson",
    );
    expect(screen.queryByRole("heading", { name: "Last attempt" })).not.toBeInTheDocument();
  });

  it("opens the quiz history page with the performance chart", async () => {
    const user = userEvent.setup();
    renderLesson();

    await screen.findByRole("heading", { name: "Last attempt" });
    await user.click(screen.getByRole("link", { name: /Show full history/i }));

    expect(screen.queryByText("Loading quiz history…")).not.toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Quiz history" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Performance over time" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "All attempts" })).toBeInTheDocument();
    expect(screen.getAllByText("#2").length).toBeGreaterThan(0);
    expect(screen.getByText(/Not passed · 40%/)).toBeInTheDocument();
  });

  it("starts review slides from the beginning", async () => {
    renderLesson("/subjects/subj-1/subtopics/st-1/lesson/slides?from=start");

    expect(await screen.findByRole("heading", { name: "Introduction" })).toBeInTheDocument();
    expect(screen.getByText("Intro content.")).toBeInTheDocument();
  });
});

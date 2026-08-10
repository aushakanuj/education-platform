import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { LessonPage } from "./LessonPage";

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

function renderLesson() {
  return render(
    <MemoryRouter
      initialEntries={["/subjects/subj-1/subtopics/st-1/lesson"]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route
          path="/subjects/:subjectId/subtopics/:subtopicId/lesson"
          element={<LessonPage />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("LessonPage", () => {
  it("shows lesson tab with summary before slides", async () => {
    renderLesson();

    expect(await screen.findByRole("heading", { name: "Lesson Summary" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Lesson" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("link", { name: /Back to subject/i })).toHaveAttribute(
      "href",
      "/subjects/subj-1",
    );
    expect(screen.getByText(/Rectangle Definition/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue · 2/3" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Start from beginning/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Next slide" })).not.toBeInTheDocument();
    expect(screen.queryByText("Subtopic quiz")).not.toBeInTheDocument();
  });

  it("opens slides when continuing the lesson", async () => {
    const user = userEvent.setup();
    renderLesson();

    await screen.findByRole("heading", { name: "Lesson Summary" });
    await user.click(screen.getByRole("button", { name: "Continue · 2/3" }));

    expect(await screen.findByRole("heading", { name: "Rectangles" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next slide" })).toBeInTheDocument();
  });

  it("shows quiz dashboard with history and performance chart", async () => {
    const user = userEvent.setup();
    renderLesson();

    await screen.findByRole("heading", { name: "Lesson Summary" });
    await user.click(screen.getByRole("tab", { name: "Quiz" }));

    expect(screen.getByRole("tab", { name: "Quiz" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { name: "Quiz" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Last quiz" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Performance over time" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Quiz history" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Retake quiz" })).toHaveAttribute("href", "/quizzes/quiz-1");
    expect(screen.getAllByText(/Not passed · 50%/).length).toBeGreaterThan(0);
  });

  it("opens the quiz tab when tab=quiz is in the URL", async () => {
    render(
      <MemoryRouter
        initialEntries={["/subjects/subj-1/subtopics/st-1/lesson?tab=quiz"]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route
            path="/subjects/:subjectId/subtopics/:subtopicId/lesson"
            element={<LessonPage />}
          />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("tab", { name: "Quiz" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { name: "Quiz history" })).toBeInTheDocument();
  });
});

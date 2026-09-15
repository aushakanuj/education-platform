import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { GenerationOutlineNode, GenerationRun } from "../../api/types";
import { GenerationRunsPage } from "./GenerationRunsPage";

vi.mock("../../auth/AuthContext", () => ({
  useAuth: () => ({
    isDevMockSession: false,
    hasRole: () => false,
  }),
}));

vi.mock("../../api/generation", () => ({
  listTopicGenerationRuns: vi.fn(),
  discardGenerationRun: vi.fn(),
  retryGenerationRun: vi.fn(),
  subscribeGenerationRun: vi.fn(),
  submitTopicGenerationRun: vi.fn(),
  getGenerationRun: vi.fn(),
  getGenerationReview: vi.fn(),
  submitReviewDecision: vi.fn(),
  closeReviewRound: vi.fn(),
  publishGenerationRun: vi.fn(),
  rejectGenerationItems: vi.fn(),
  isInFlightGenerationPhase: (phase: string) =>
    phase === "indexing" ||
    phase === "outlining" ||
    phase === "outline_review" ||
    phase === "generating" ||
    phase === "qa_review",
}));

import {
  getGenerationReview,
  getGenerationRun,
  listTopicGenerationRuns,
  submitReviewDecision,
} from "../../api/generation";
import type { ReviewWorkspace } from "../../api/types";

function node(over: Partial<GenerationOutlineNode> = {}): GenerationOutlineNode {
  return {
    id: "node-1",
    parent_id: null,
    slug: "fractions",
    title: "Fractions",
    token_mass: 120,
    prerequisite_score: "0.10",
    centrality: "0.40",
    weight: "0.5000",
    quota: 40,
    matched_subtopic_id: null,
    force_create: false,
    accepted_subtopic_id: null,
    proposed_outcomes: ["Add like fractions"],
    sequence: 1,
    ...over,
  };
}

function run(over: Partial<GenerationRun> = {}): GenerationRun {
  return {
    id: "run-1",
    topic_id: "topic-1",
    title: "Unit source",
    phase: "outline_review",
    target_item_count: 80,
    submitted_by_user_id: "u1",
    intake_version_id: "v1",
    failure_reason: null,
    outline: {
      target_item_count: 80,
      nodes: [node()],
    },
    draft_lesson_markdown: null,
    jobs: [],
    created_at: "2026-09-09T00:00:00Z",
    ...over,
  };
}

function workspace(over: Partial<ReviewWorkspace> = {}): ReviewWorkspace {
  return {
    run_id: "run-1",
    topic_id: "topic-1",
    phase: "outline_review",
    published_locked: false,
    viewer_is_closer: false,
    active_revision: {
      stage: "outline",
      id: "rev-1",
      run_id: "run-1",
      number: 1,
      parent_id: null,
      origin: "initial_generation",
      snapshot_hash: "abc",
      created_at: "2026-09-13T00:00:00Z",
      created_by: { display_name: "outline", occurred_at: "2026-09-13T00:00:00Z" },
      snapshot: {
        target_item_count: 80,
        nodes: [
          {
            node_key: "node-1",
            parent_node_key: null,
            slug: "fractions",
            title: "Fractions",
            token_mass: 120,
            prerequisite_score: "0.10",
            centrality: "0.40",
            weight: "0.5000",
            matched_subtopic_id: null,
            force_create: false,
            proposed_outcomes: ["Add like fractions"],
            sequence: 1,
          },
        ],
      },
    },
    diff_from_parent: null,
    open_round: {
      id: "round-1",
      run_id: "run-1",
      revision_id: "rev-1",
      stage: "outline",
      number: 1,
      opened_at: "2026-09-13T00:00:00Z",
      due_at: "2026-09-16T00:00:00Z",
      sealed_at: null,
    },
    reviewer_states: [],
    request_threads: [],
    history: [],
    ...over,
  };
}

function renderPage() {
  return render(
    <MemoryRouter
      initialEntries={["/teacher/topics/topic-1/generation"]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route path="/teacher/topics/:topicId/generation" element={<GenerationRunsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("GenerationRunsPage", () => {
  beforeEach(() => {
    vi.mocked(listTopicGenerationRuns).mockReset();
    vi.mocked(getGenerationReview).mockReset();
    vi.mocked(submitReviewDecision).mockReset();
    vi.mocked(getGenerationRun).mockReset();
    vi.mocked(listTopicGenerationRuns).mockResolvedValue([run()]);
    vi.mocked(getGenerationReview).mockResolvedValue(workspace());
  });

  it("loads the review board and hides PDF upload", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "Topic generation review" })).toBeInTheDocument();
    expect(await screen.findByText("Sequence 1: Fractions")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve outline" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save outline" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Accept current outline" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Override and accept" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Discard run" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("PDF file")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Upload topic PDF" })).not.toBeInTheDocument();
    expect(listTopicGenerationRuns).toHaveBeenCalledWith("topic-1");
    expect(getGenerationReview).toHaveBeenCalledWith("run-1");
  });

  it("submits an approval through the review decision API", async () => {
    const user = userEvent.setup();
    vi.mocked(submitReviewDecision).mockResolvedValue({
      id: "dec-1",
      round_id: "round-1",
      revision_id: "rev-1",
      verdict: "approve",
      reviewer: { display_name: "Meera Krishnan", occurred_at: "2026-09-13T00:00:00Z" },
      requests: [],
    });
    vi.mocked(getGenerationRun).mockResolvedValue(run());

    renderPage();
    await screen.findByText("Sequence 1: Fractions");
    await user.click(screen.getByRole("button", { name: "Approve outline" }));

    expect(submitReviewDecision).toHaveBeenCalledWith("run-1", "round-1", {
      revision_id: "rev-1",
      verdict: "approve",
      snapshot_hash: "abc",
    });
  });

  it("shows QA keys without a publish control for teachers", async () => {
    vi.mocked(listTopicGenerationRuns).mockResolvedValue([
      run({
        phase: "qa_review",
        draft_lesson_markdown: "# Lesson",
        qa_items: [
          {
            question_id: "q-1",
            question_version_id: "qv-1",
            prompt: "Teacher-visible stem",
            options: { A: "1", B: "2" },
            correct_label: "A",
            correct_rationale: "Because two halves make one.",
            distractor_rationales: { B: "Too large." },
            subtopic_id: "st-1",
            sequence: 1,
          },
        ],
      }),
    ]);

    renderPage();

    expect(await screen.findByText("Teacher-visible stem")).toBeInTheDocument();
    expect(screen.getByText("Because two halves make one.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Publish to students" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("PDF file")).not.toBeInTheDocument();
  });
});

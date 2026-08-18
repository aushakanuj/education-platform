import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { QuestionBankPage } from "./QuestionBankPage";
import type { DraftQuestion } from "../../api/authoring";

const fetchAuthorableSubtopics = vi.fn();
const fetchDrafts = vi.fn();
const fetchApproved = vi.fn();
const publishDraft = vi.fn();
const discardDraft = vi.fn();
const generateQuestions = vi.fn();

vi.mock("../../api/authoring", () => ({
  fetchAuthorableSubtopics: () => fetchAuthorableSubtopics(),
  fetchDrafts: (...a: unknown[]) => fetchDrafts(...a),
  fetchApproved: (...a: unknown[]) => fetchApproved(...a),
  publishDraft: (...a: unknown[]) => publishDraft(...a),
  discardDraft: (...a: unknown[]) => discardDraft(...a),
  generateQuestions: (...a: unknown[]) => generateQuestions(...a),
}));

function question(over: Partial<DraftQuestion> = {}): DraftQuestion {
  return {
    id: "d1",
    prompt: "What is 3/4 + 1/4?",
    options: [
      { label: "A", text: "1" },
      { label: "B", text: "1/2" },
      { label: "C", text: "2/4" },
      { label: "D", text: "5/4" },
    ],
    correct_label: "A",
    explanation: null,
    difficulty: "easy",
    ...over,
  };
}

function renderPage() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QuestionBankPage />
    </MemoryRouter>,
  );
}

describe("QuestionBankPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchAuthorableSubtopics.mockResolvedValue([
      {
        id: "s1",
        name: "Fractions",
        subject: "Mathematics",
        topic: "Number",
        draft_count: 1,
        published_count: 2,
      },
    ]);
    fetchDrafts.mockResolvedValue([question()]);
    fetchApproved.mockResolvedValue([
      question({ id: "p1", prompt: "What is 1/2 of 10?" }),
      question({ id: "p2", prompt: "Simplify 6/8." }),
    ]);
  });

  it("counts both what is waiting and what is already approved", async () => {
    renderPage();
    expect(await screen.findByRole("tab", { name: "Awaiting approval (1)" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Approved (2)" })).toBeInTheDocument();
  });

  it("opens on the drafts, where the work is", async () => {
    renderPage();
    expect(await screen.findByText("What is 3/4 + 1/4?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
  });

  it("shows the approved bank, without approve buttons, when that tab is chosen", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("What is 3/4 + 1/4?");

    await user.click(screen.getByRole("tab", { name: "Approved (2)" }));

    expect(screen.getByText("What is 1/2 of 10?")).toBeInTheDocument();
    expect(screen.getByText("Simplify 6/8.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("offers the download only once something has been approved", async () => {
    const user = userEvent.setup();
    fetchApproved.mockResolvedValue([]);
    renderPage();
    await screen.findByText("What is 3/4 + 1/4?");

    await user.click(screen.getByRole("tab", { name: "Approved (0)" }));

    expect(screen.queryByRole("button", { name: "Download as CSV" })).not.toBeInTheDocument();
    expect(screen.getByText(/Nothing approved for this subtopic yet/)).toBeInTheDocument();
  });

  it("moves an approved draft across so it is not lost from view", async () => {
    const user = userEvent.setup();
    publishDraft.mockResolvedValue(undefined);
    renderPage();
    await screen.findByText("What is 3/4 + 1/4?");

    await user.click(screen.getByRole("button", { name: "Approve" }));

    expect(await screen.findByRole("tab", { name: "Awaiting approval (0)" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Approved (3)" })).toBeInTheDocument();
    expect(screen.getByText(/It is in the Approved tab now/)).toBeInTheDocument();
  });

  it("says a discard was archived, not deleted", async () => {
    const user = userEvent.setup();
    discardDraft.mockResolvedValue(undefined);
    renderPage();
    await screen.findByText("What is 3/4 + 1/4?");

    await user.click(screen.getByRole("button", { name: "Discard" }));

    expect(await screen.findByText(/archived, not deleted/)).toBeInTheDocument();
  });
});

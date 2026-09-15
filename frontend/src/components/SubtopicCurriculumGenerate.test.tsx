import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CurriculumGenerationJob } from "../api/types";
import type { AdminSubtopic } from "../lib/adminCurriculumLive";
import { SubtopicCurriculumGenerateList } from "./SubtopicCurriculumGenerate";

vi.mock("../api/generation", () => ({
  enqueueCurriculumGeneration: vi.fn(),
  pollCurriculumGenerationJob: vi.fn(),
  isInFlightCurriculumGenerationStatus: (status: string) =>
    status === "queued" || status === "running",
  isTerminalCurriculumGenerationStatus: (status: string) =>
    status === "succeeded" || status === "failed",
}));

import { enqueueCurriculumGeneration, pollCurriculumGenerationJob } from "../api/generation";

function job(over: Partial<CurriculumGenerationJob> = {}): CurriculumGenerationJob {
  return {
    id: "job-1",
    subtopic_id: "st-1-uuid",
    status: "queued",
    round_count: 0,
    reviewer_notes: null,
    error: null,
    source_material_version_id: null,
    quiz_version_id: null,
    ...over,
  };
}

const subtopic: AdminSubtopic = {
  id: "st-1-uuid",
  title: "Place value",
  order: 1,
  lesson: null,
  quiz: null,
};

describe("SubtopicCurriculumGenerateList", () => {
  beforeEach(() => {
    vi.mocked(enqueueCurriculumGeneration).mockReset();
    vi.mocked(pollCurriculumGenerationJob).mockReset();
  });

  it("mentions that a curriculum PDF must be ingested first", () => {
    render(<SubtopicCurriculumGenerateList subtopics={[subtopic]} onSucceeded={() => {}} />);

    expect(
      screen.getByText(/Requires a curriculum PDF uploaded and ingested/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate lesson & quiz" })).toBeInTheDocument();
  });

  it("polls until success, shows reviewer notes, and refreshes", async () => {
    const user = userEvent.setup();
    const onSucceeded = vi.fn();
    vi.mocked(enqueueCurriculumGeneration).mockResolvedValue(job());
    vi.mocked(pollCurriculumGenerationJob).mockImplementation(async (_id, options) => {
      options?.onUpdate?.(job({ status: "running", round_count: 1 }));
      return job({
        status: "succeeded",
        round_count: 2,
        reviewer_notes: "Approved after a worked example was added.",
        source_material_version_id: "mv-1",
        quiz_version_id: "qv-1",
      });
    });

    render(<SubtopicCurriculumGenerateList subtopics={[subtopic]} onSucceeded={onSucceeded} />);
    await user.click(screen.getByRole("button", { name: "Generate lesson & quiz" }));

    expect(enqueueCurriculumGeneration).toHaveBeenCalledWith("st-1-uuid");
    expect(await screen.findByText("Approved after a worked example was added.")).toBeInTheDocument();
    expect(screen.getByText("Generated")).toBeInTheDocument();
    expect(screen.getByText("2 review rounds")).toBeInTheDocument();
    expect(onSucceeded).toHaveBeenCalledTimes(1);
  });

  it("shows failure notes without refreshing", async () => {
    const user = userEvent.setup();
    const onSucceeded = vi.fn();
    vi.mocked(enqueueCurriculumGeneration).mockResolvedValue(job());
    vi.mocked(pollCurriculumGenerationJob).mockResolvedValue(
      job({
        status: "failed",
        error: "No ingested chunks for this subtopic.",
        reviewer_notes: "Cannot review without source material.",
      }),
    );

    render(<SubtopicCurriculumGenerateList subtopics={[subtopic]} onSucceeded={onSucceeded} />);
    await user.click(screen.getByRole("button", { name: "Generate lesson & quiz" }));

    expect(await screen.findByText("No ingested chunks for this subtopic.")).toBeInTheDocument();
    expect(screen.getByText("Cannot review without source material.")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(onSucceeded).not.toHaveBeenCalled();
  });

  it("shows request errors from enqueue", async () => {
    const user = userEvent.setup();
    vi.mocked(enqueueCurriculumGeneration).mockRejectedValue(new Error("Request failed (403)"));

    render(<SubtopicCurriculumGenerateList subtopics={[subtopic]} onSucceeded={() => {}} />);
    await user.click(screen.getByRole("button", { name: "Generate lesson & quiz" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not generate the lesson and quiz.");
    await waitFor(() => {
      expect(pollCurriculumGenerationJob).not.toHaveBeenCalled();
    });
  });
});

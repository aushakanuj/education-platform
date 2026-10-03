import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ItemStatFlag, TopicItemStat, TopicItemStats as TopicItemStatsReport } from "../api/types";
import { TopicItemStats } from "./TopicItemStats";

vi.mock("../api/generation", () => ({
  fetchTopicItemStats: vi.fn(),
}));

import { fetchTopicItemStats } from "../api/generation";

const FLAGS: ItemStatFlag[] = [
  "too_easy",
  "too_hard",
  "low_discrimination",
  "negative_discrimination",
  "dead_distractor",
  "distractor_beats_key_top_group",
];

function stat(over: Partial<TopicItemStat> = {}): TopicItemStat {
  return {
    question_version_id: "qv-1",
    sequence: 1,
    prompt: "What is 1/2 + 1/2?",
    correct_option_label: "A",
    n: 20,
    p_correct: 0.5,
    discrimination: 0.42,
    options: [
      {
        label: "A",
        text: "1",
        is_key: true,
        pick_rate: 0.5,
        top_group_pick_rate: 0.8,
        bottom_group_pick_rate: 0.2,
      },
      {
        label: "B",
        text: "2",
        is_key: false,
        pick_rate: 0.5,
        top_group_pick_rate: 0.2,
        bottom_group_pick_rate: 0.8,
      },
    ],
    flags: ["low_discrimination"],
    ...over,
  };
}

function report(items: TopicItemStat[], minimum = 20): TopicItemStatsReport {
  return {
    topic_id: "topic-1",
    quiz_version_id: "quiz-1",
    minimum_n: minimum,
    items,
  };
}

describe("TopicItemStats", () => {
  beforeEach(() => {
    vi.mocked(fetchTopicItemStats).mockReset();
  });

  it("shows a loading state until stats arrive", () => {
    vi.mocked(fetchTopicItemStats).mockReturnValue(new Promise(() => undefined));
    render(<TopicItemStats topicId="topic-1" />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading item statistics");
  });

  it("shows an empty state when the quiz has no items", async () => {
    vi.mocked(fetchTopicItemStats).mockResolvedValue(report([]));
    render(<TopicItemStats topicId="topic-1" />);

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Not enough responses to flag items yet. Flags start once a question has at least 20 responses.",
    );
    expect(fetchTopicItemStats).toHaveBeenCalledWith("topic-1");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("stays empty when every item is below the minimum response count", async () => {
    vi.mocked(fetchTopicItemStats).mockResolvedValue(
      report([stat({ n: 4, prompt: "Too few answers", flags: [] })]),
    );
    render(<TopicItemStats topicId="topic-1" />);

    expect(await screen.findByText(/Not enough responses to flag items yet/)).toBeInTheDocument();
    expect(screen.queryByText("Too few answers")).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("renders qualifying items with flag badges and hides the rest", async () => {
    vi.mocked(fetchTopicItemStats).mockResolvedValue(
      report([
        stat({
          question_version_id: "qv-low",
          sequence: 2,
          prompt: "Still collecting",
          n: 3,
          flags: [],
        }),
        stat({
          question_version_id: "qv-flags",
          sequence: 1,
          prompt: "What is 1/2 + 1/2?",
          flags: FLAGS,
          discrimination: -0.2,
          p_correct: 0.1,
        }),
      ]),
    );
    render(<TopicItemStats topicId="topic-1" />);

    expect(await screen.findByRole("table")).toBeInTheDocument();
    expect(screen.getByText("What is 1/2 + 1/2?")).toBeInTheDocument();
    expect(screen.queryByText("Still collecting")).not.toBeInTheDocument();
    expect(screen.getByText("A (key) 50.0% · B 50.0%")).toBeInTheDocument();
    expect(screen.getByText("10.0%")).toBeInTheDocument();
    expect(screen.getByText("-0.20")).toBeInTheDocument();
    expect(screen.getByText("Too easy")).toBeInTheDocument();
    expect(screen.getByText("Too hard")).toBeInTheDocument();
    expect(screen.getByText("Low discrimination")).toBeInTheDocument();
    expect(screen.getByText("Negative discrimination")).toBeInTheDocument();
    expect(screen.getByText("Dead distractor")).toBeInTheDocument();
    expect(screen.getByText("Distractor beats key")).toBeInTheDocument();
    expect(screen.getAllByText("Too easy")[0]).toHaveClass("badge", "badge--warn");
  });

  it("shows an unflagged qualifying item as none", async () => {
    vi.mocked(fetchTopicItemStats).mockResolvedValue(
      report([stat({ flags: [], discrimination: null, p_correct: null })]),
    );
    render(<TopicItemStats topicId="topic-1" />);

    expect(await screen.findByText("None")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("reports a load failure", async () => {
    vi.mocked(fetchTopicItemStats).mockRejectedValue(new Error("offline"));
    render(<TopicItemStats topicId="topic-1" />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load item statistics.");
  });
});

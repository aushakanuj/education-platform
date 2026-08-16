import { describe, expect, it } from "vitest";

import { quizActionLabel, trackedAttempts } from "./quizAction";

describe("quizActionLabel", () => {
  it("starts a fresh quiz when nothing has been submitted", () => {
    expect(quizActionLabel(null)).toBe("Start quiz");
    expect(
      quizActionLabel({
        recent_attempts: [{ status: "in_progress" }],
      } as never),
    ).toBe("Start quiz");
    expect(
      quizActionLabel({
        recent_attempts: [{ status: "abandoned" }],
      } as never),
    ).toBe("Start quiz");
  });

  it("retakes after a finished attempt", () => {
    expect(
      quizActionLabel({
        recent_attempts: [{ status: "scored" }],
      } as never),
    ).toBe("Retake quiz");
  });
});

describe("trackedAttempts", () => {
  it("drops abandoned attempts so they are not kept in history", () => {
    expect(
      trackedAttempts([
        { id: "a", status: "abandoned" },
        { id: "b", status: "scored" },
        { id: "c", status: "in_progress" },
      ] as never),
    ).toEqual([
      { id: "b", status: "scored" },
      { id: "c", status: "in_progress" },
    ]);
  });
});

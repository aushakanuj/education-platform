import { describe, expect, it } from "vitest";

import { quizActionLabel } from "./quizAction";

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

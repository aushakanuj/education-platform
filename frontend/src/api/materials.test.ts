import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./client", () => ({
  apiRequest: vi.fn(),
}));

import { apiRequest } from "./client";
import { getTopicMaterial } from "./materials";

describe("materials helpers", () => {
  beforeEach(() => {
    vi.mocked(apiRequest).mockReset();
  });

  it("loads a published topic lesson from GET /topics/{id}/material", async () => {
    vi.mocked(apiRequest).mockResolvedValue({
      id: "topic-1",
      title: "Topic lesson",
      markdown: "# Lesson",
      slides: [],
      progress: null,
      source_material_version_id: "v1",
      quiz_unlocked: true,
      quiz_id: "quiz-1",
    });

    const lesson = await getTopicMaterial("topic-1");

    expect(lesson.markdown).toBe("# Lesson");
    expect(apiRequest).toHaveBeenCalledWith("/topics/topic-1/material");
  });
});

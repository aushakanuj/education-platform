import { describe, expect, it, vi } from "vitest";

import { ApiError } from "./types";

vi.mock("./client", () => ({
  apiStream: vi.fn(),
}));

import { apiStream } from "./client";
import { runSubject, subscribeProgress, watchProgress } from "./progress";
import type { GenerationRun } from "./types";

function runFixture(over: Partial<GenerationRun> = {}): GenerationRun {
  return {
    id: "run-1",
    topic_id: "topic-1",
    title: "Unit source",
    phase: "indexing",
    target_item_count: 80,
    submitted_by_user_id: "u1",
    intake_version_id: "v1",
    failure_reason: null,
    outline: null,
    draft_lesson_markdown: null,
    jobs: [],
    created_at: "2026-09-13T00:00:00Z",
    ...over,
  };
}

function streamResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  let index = 0;
  const body = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (index >= chunks.length) {
        controller.close();
        return;
      }
      controller.enqueue(encoder.encode(chunks[index]));
      index += 1;
    },
  });
  return new Response(body, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

describe("progress SSE client", () => {
  it("emits snapshots and stops on close", async () => {
    const onSnapshot = vi.fn();
    vi.mocked(apiStream).mockResolvedValue(
      streamResponse([
        'id: run-1:abc\nevent: snapshot\ndata: {"id":"run-1","phase":"indexing"}\n\n',
        'event: snapshot\ndata: {"id":"run-1","phase":"failed"}\n\n',
        'event: close\ndata: {"reason":"terminal"}\n\n',
      ]),
    );

    await subscribeProgress(runSubject("run-1"), { onSnapshot });

    expect(apiStream).toHaveBeenCalledWith("/progress/runs/run-1", {
      signal: undefined,
      lastEventId: undefined,
    });
    expect(onSnapshot.mock.calls.map((call) => call[0]?.phase)).toEqual(["indexing", "failed"]);
  });

  it("returns the last snapshot from watchProgress", async () => {
    vi.mocked(apiStream).mockResolvedValue(
      streamResponse([
        `event: snapshot\ndata: ${JSON.stringify(runFixture({ phase: "failed" }))}\n\n`,
        'event: close\ndata: {"reason":"terminal"}\n\n',
      ]),
    );
    const snapshot = await watchProgress(runSubject("run-1"));
    expect((snapshot as GenerationRun).phase).toBe("failed");
  });

  it("raises stream error events", async () => {
    vi.mocked(apiStream).mockResolvedValue(
      streamResponse(['event: error\ndata: {"detail":"gone","status":404}\n\n']),
    );
    await expect(subscribeProgress(runSubject("run-1"), { onSnapshot: vi.fn() })).rejects.toBeInstanceOf(
      ApiError,
    );
  });
});

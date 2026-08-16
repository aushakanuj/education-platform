import { afterEach, describe, expect, it, vi } from "vitest";

import { createDoodleEngine, VIGNETTES } from "./doodleEngine";

function mockCtx() {
  return {
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(),
    arc: vi.fn(),
    fillText: vi.fn(),
    measureText: vi.fn(() => ({ width: 8 })),
    setLineDash: vi.fn(),
    strokeStyle: "",
    fillStyle: "",
    lineWidth: 1,
    lineCap: "round",
    lineJoin: "round",
    globalAlpha: 1,
    font: "",
  } as unknown as CanvasRenderingContext2D;
}

describe("createDoodleEngine", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("exposes education vignettes", () => {
    expect(Object.keys(VIGNETTES)).toEqual(
      expect.arrayContaining(["openBook", "pencil", "atom", "geometry", "flask", "lightbulb", "abacus", "globe"]),
    );
  });

  it("ticks and disposes without throwing", () => {
    vi.useFakeTimers();
    const engine = createDoodleEngine();
    engine.resize(800, 600);
    const ctx = mockCtx();
    expect(() => engine.tick(ctx, Date.now())).not.toThrow();
    vi.advanceTimersByTime(3000);
    expect(() => engine.tick(ctx, Date.now())).not.toThrow();
    expect(() => engine.dispose()).not.toThrow();
  });
});

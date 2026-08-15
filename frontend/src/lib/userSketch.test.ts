import { describe, expect, it, vi } from "vitest";

import { canStartSketch, createUserSketch } from "./userSketch";

function mockCtx() {
  return {
    save: vi.fn(),
    restore: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    quadraticCurveTo: vi.fn(),
    stroke: vi.fn(),
    strokeRect: vi.fn(),
    fillRect: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    fillText: vi.fn(),
    measureText: vi.fn((text: string) => ({ width: text.length * 7 })),
    setLineDash: vi.fn(),
    strokeStyle: "",
    fillStyle: "",
    lineWidth: 1,
    lineCap: "round",
    lineJoin: "round",
    font: "",
    textAlign: "left",
    textBaseline: "alphabetic",
  } as unknown as CanvasRenderingContext2D;
}

describe("userSketch", () => {
  it("ignores interactive targets", () => {
    const button = document.createElement("button");
    document.body.append(button);
    expect(canStartSketch(button)).toBe(false);
    const empty = document.createElement("div");
    document.body.append(empty);
    expect(canStartSketch(empty)).toBe(true);
    button.remove();
    empty.remove();
  });

  it("records a smoothed stroke and paints it", () => {
    const sketch = createUserSketch();
    const ctx = mockCtx();
    sketch.resize(800, 600);
    sketch.begin(80, 80, 1_000);
    sketch.extend(200, 280, 1_016);
    sketch.extend(240, 300, 1_032);
    sketch.extend(280, 280, 1_048);
    sketch.end(400, 80, 1_064);
    expect(sketch.isDrawing()).toBe(false);
    sketch.tick(ctx, 1_100);
    expect(ctx.stroke).toHaveBeenCalled();
    expect(ctx.fillText).not.toHaveBeenCalledWith(
      expect.stringMatching(/^y =|^x =/),
      expect.any(Number),
      expect.any(Number),
    );
    sketch.dispose();
  });

  it("straightens a line and paints its Cartesian equation", () => {
    const sketch = createUserSketch();
    const ctx = mockCtx();
    sketch.resize(800, 600);
    sketch.begin(400, 300, 1_000);
    sketch.extend(440, 262, 1_016);
    sketch.extend(480, 218, 1_032);
    sketch.extend(520, 182, 1_048);
    sketch.end(560, 140, 1_064);
    expect(sketch.isDrawing()).toBe(false);
    sketch.tick(ctx, 1_100);
    expect(ctx.lineTo).toHaveBeenCalled();
    expect(ctx.fillText).toHaveBeenCalledWith("y = x", expect.any(Number), expect.any(Number));
    expect(ctx.fillText).toHaveBeenCalledWith(
      expect.stringContaining("m = 1"),
      expect.any(Number),
      expect.any(Number),
    );
    expect(ctx.fillText).toHaveBeenCalledWith("(0, 0)", expect.any(Number), expect.any(Number));
    sketch.dispose();
  });
});

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
    closePath: vi.fn(),
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
      expect.stringMatching(/^y =|^x =|^r =|^length =/),
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

  it("snaps a circle and paints radius, diameter, and area", () => {
    const sketch = createUserSketch();
    const ctx = mockCtx();
    sketch.resize(800, 600);
    const n = 36;
    for (let i = 0; i < n; i += 1) {
      const angle = (i / (n - 1)) * Math.PI * 2;
      const x = 400 + 80 * Math.cos(angle);
      const y = 300 + 80 * Math.sin(angle);
      if (i === 0) sketch.begin(x, y, 1_000);
      else if (i === n - 1) sketch.end(x, y, 1_000 + i * 16);
      else sketch.extend(x, y, 1_000 + i * 16);
    }
    sketch.tick(ctx, 1_600);
    expect(ctx.arc).toHaveBeenCalled();
    expect(ctx.fillText).toHaveBeenCalledWith("x² + y² = 4", expect.any(Number), expect.any(Number));
    expect(ctx.fillText).toHaveBeenCalledWith(
      expect.stringContaining("r = 2"),
      expect.any(Number),
      expect.any(Number),
    );
    expect(ctx.fillText).toHaveBeenCalledWith(
      expect.stringContaining("d = 4"),
      expect.any(Number),
      expect.any(Number),
    );
    expect(ctx.fillText).toHaveBeenCalledWith(
      expect.stringMatching(/^A ≈ /),
      expect.any(Number),
      expect.any(Number),
    );
    sketch.dispose();
  });

  it("snaps a triangle and paints length, height, area, and diameter", () => {
    const sketch = createUserSketch();
    const ctx = mockCtx();
    sketch.resize(800, 600);
    const vertices = [
      { x: 400, y: 180 },
      { x: 560, y: 420 },
      { x: 240, y: 420 },
      { x: 400, y: 180 },
    ];
    let t = 1_000;
    sketch.begin(vertices[0]!.x, vertices[0]!.y, t);
    for (let i = 0; i < vertices.length - 1; i += 1) {
      const a = vertices[i]!;
      const b = vertices[i + 1]!;
      for (let s = 1; s <= 8; s += 1) {
        t += 16;
        const x = a.x + ((b.x - a.x) * s) / 8;
        const y = a.y + ((b.y - a.y) * s) / 8;
        if (i === vertices.length - 2 && s === 8) sketch.end(x, y, t);
        else sketch.extend(x, y, t);
      }
    }
    sketch.tick(ctx, 1_600);
    expect(ctx.closePath).toHaveBeenCalled();
    expect(ctx.fillText).toHaveBeenCalledWith(
      expect.stringContaining("length ="),
      expect.any(Number),
      expect.any(Number),
    );
    expect(ctx.fillText).toHaveBeenCalledWith(
      expect.stringContaining("A ="),
      expect.any(Number),
      expect.any(Number),
    );
    expect(ctx.fillText).toHaveBeenCalledWith(
      expect.stringContaining("d ="),
      expect.any(Number),
      expect.any(Number),
    );
    sketch.dispose();
  });
});

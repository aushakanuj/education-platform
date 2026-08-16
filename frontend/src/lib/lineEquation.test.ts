import { describe, expect, it } from "vitest";

import {
  clipLineToRect,
  describeLine,
  fitStraightLine,
  formatCoeff,
  GRID_UNIT,
  screenToMath,
} from "./lineEquation";

const VIEW = { width: 800, height: 600, unit: GRID_UNIT };

describe("screenToMath", () => {
  it("places the canvas center at the origin with y up", () => {
    expect(screenToMath({ x: 400, y: 300 }, VIEW)).toEqual({ x: 0, y: 0 });
    expect(screenToMath({ x: 440, y: 260 }, VIEW)).toEqual({ x: 1, y: 1 });
    expect(screenToMath({ x: 360, y: 340 }, VIEW)).toEqual({ x: -1, y: -1 });
  });
});

describe("formatCoeff", () => {
  it("trims trailing zeros and avoids negative zero", () => {
    expect(formatCoeff(1.5)).toBe("1.5");
    expect(formatCoeff(2)).toBe("2");
    expect(formatCoeff(-0.0001)).toBe("0");
  });
});

describe("fitStraightLine", () => {
  it("fits a wobbly near-horizontal stroke", () => {
    const fitted = fitStraightLine([
      { x: 120, y: 302 },
      { x: 200, y: 297 },
      { x: 280, y: 304 },
      { x: 360, y: 298 },
      { x: 440, y: 301 },
    ]);
    expect(fitted).not.toBeNull();
    expect(fitted!.end.x - fitted!.start.x).toBeGreaterThan(200);
    expect(Math.abs(fitted!.end.y - fitted!.start.y)).toBeLessThan(12);
  });

  it("rejects a curved stroke that is not a line", () => {
    expect(
      fitStraightLine([
        { x: 100, y: 300 },
        { x: 150, y: 180 },
        { x: 250, y: 120 },
        { x: 350, y: 180 },
        { x: 400, y: 300 },
      ]),
    ).toBeNull();
  });

  it("rejects a tap-sized stroke", () => {
    expect(
      fitStraightLine([
        { x: 400, y: 300 },
        { x: 410, y: 304 },
      ]),
    ).toBeNull();
  });
});

describe("describeLine", () => {
  it("describes y = x through the origin", () => {
    const line = describeLine({ x: 400, y: 300 }, { x: 480, y: 220 }, VIEW);
    expect(line.equation).toBe("y = x");
    expect(line.slope).toBe(1);
    expect(line.overlay[0]).toBe("y = x");
    expect(line.overlay.some((row) => row.includes("origin"))).toBe(true);
  });

  it("describes a vertical line as x = a", () => {
    const line = describeLine({ x: 480, y: 140 }, { x: 480, y: 460 }, VIEW);
    expect(line.equation).toBe("x = 2");
    expect(line.slope).toBeNull();
    expect(line.slopeLabel).toContain("vertical");
  });

  it("describes slope-intercept with intercepts", () => {
    // start (0, 1): screen (400, 260); end (2, 5): screen (480, 100) → y = 2x + 1
    const line = describeLine({ x: 400, y: 260 }, { x: 480, y: 100 }, VIEW);
    expect(line.equation).toBe("y = 2x + 1");
    expect(line.slope).toBe(2);
    expect(line.yIntercept).toBeCloseTo(1);
    expect(line.xIntercept).toBeCloseTo(-0.5);
  });

  it("describes a horizontal line as y = b", () => {
    const line = describeLine({ x: 200, y: 220 }, { x: 600, y: 220 }, VIEW);
    expect(line.equation).toBe("y = 2");
    expect(line.slope).toBeCloseTo(0);
  });
});

describe("clipLineToRect", () => {
  it("extends a diagonal across the viewport", () => {
    const clipped = clipLineToRect({ x: 400, y: 300 }, { x: 1, y: -1 }, 800, 600);
    expect(clipped).not.toBeNull();
    const [a, b] = clipped!;
    expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeGreaterThan(500);
    expect([a.y, b.y].sort((left, right) => left - right)).toEqual([0, 600]);
  });
});

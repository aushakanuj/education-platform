import { describe, expect, it } from "vitest";

import { GRID_UNIT, type ScreenPoint } from "./lineEquation";
import { describeCircle, describeTriangle, fitCircle, fitTriangle } from "./shapeFit";

const VIEW = { width: 800, height: 600, unit: GRID_UNIT };

function circleStroke(cx: number, cy: number, r: number, n = 36, wobble = 1.5): ScreenPoint[] {
  return Array.from({ length: n }, (_, i) => {
    const angle = (i / (n - 1)) * Math.PI * 2;
    const jitter = ((i % 5) - 2) * (wobble / 2);
    return {
      x: cx + (r + jitter) * Math.cos(angle),
      y: cy + (r + jitter) * Math.sin(angle),
    };
  });
}

function polyline(vertices: ScreenPoint[], steps = 8, wobble = 1.2): ScreenPoint[] {
  const points: ScreenPoint[] = [];
  for (let i = 0; i < vertices.length - 1; i += 1) {
    const a = vertices[i]!;
    const b = vertices[i + 1]!;
    for (let s = 0; s < steps; s += 1) {
      const t = s / steps;
      const jitter = ((s + i) % 3) - 1;
      points.push({
        x: a.x + (b.x - a.x) * t + jitter * wobble,
        y: a.y + (b.y - a.y) * t + jitter * wobble * 0.4,
      });
    }
  }
  points.push({ ...vertices[vertices.length - 1]! });
  return points;
}

function ellipseStroke(cx: number, cy: number, rx: number, ry: number, n = 36): ScreenPoint[] {
  return Array.from({ length: n }, (_, i) => {
    const angle = (i / (n - 1)) * Math.PI * 2;
    return { x: cx + rx * Math.cos(angle), y: cy + ry * Math.sin(angle) };
  });
}

describe("fitCircle", () => {
  it("fits a wobbly closed circle", () => {
    const fitted = fitCircle(circleStroke(400, 300, 80));
    expect(fitted).not.toBeNull();
    expect(fitted!.center.x).toBeCloseTo(400, 0);
    expect(fitted!.center.y).toBeCloseTo(300, 0);
    expect(fitted!.radius).toBeCloseTo(80, 0);
  });

  it("rejects a straight stroke", () => {
    expect(
      fitCircle([
        { x: 120, y: 300 },
        { x: 200, y: 302 },
        { x: 280, y: 298 },
        { x: 360, y: 301 },
        { x: 440, y: 299 },
        { x: 520, y: 303 },
        { x: 600, y: 300 },
      ]),
    ).toBeNull();
  });

  it("fits a closed ellipse as a circle", () => {
    const fitted = fitCircle(ellipseStroke(400, 300, 90, 55));
    expect(fitted).not.toBeNull();
    expect(fitted!.center.x).toBeCloseTo(400, 0);
    expect(fitted!.center.y).toBeCloseTo(300, 0);
  });

  it("fits a sloppy closed loop", () => {
    const fitted = fitCircle(circleStroke(400, 300, 80, 36, 12));
    expect(fitted).not.toBeNull();
    expect(fitted!.radius).toBeGreaterThan(50);
  });

  it("rejects an incomplete arc", () => {
    const arc = Array.from({ length: 28 }, (_, i) => {
      const angle = (i / 27) * Math.PI * 1.5;
      return { x: 400 + 80 * Math.cos(angle), y: 300 + 80 * Math.sin(angle) };
    });
    expect(fitCircle(arc)).toBeNull();
  });
});

describe("describeCircle", () => {
  it("reports radius, diameter, and area in grid units", () => {
    const info = describeCircle({ center: { x: 400, y: 300 }, radius: 80, rms: 1 }, VIEW);
    expect(info.radius).toBeCloseTo(2);
    expect(info.diameter).toBeCloseTo(4);
    expect(info.area).toBeCloseTo(Math.PI * 4, 5);
    expect(info.equation).toBe("x² + y² = 4");
    expect(info.overlay[1]).toContain("r = 2");
    expect(info.overlay[1]).toContain("d = 4");
    expect(info.overlay[2]).toMatch(/^A ≈ /);
  });
});

describe("fitTriangle", () => {
  it("fits a wobbly closed triangle", () => {
    const fitted = fitTriangle(
      polyline([
        { x: 400, y: 180 },
        { x: 560, y: 420 },
        { x: 240, y: 420 },
        { x: 400, y: 180 },
      ]),
    );
    expect(fitted).not.toBeNull();
    expect(fitted!.vertices).toHaveLength(3);
  });

  it("rejects a circle", () => {
    expect(fitTriangle(circleStroke(400, 300, 80))).toBeNull();
  });

  it("rejects an open polyline", () => {
    expect(
      fitTriangle(
        polyline([
          { x: 200, y: 400 },
          { x: 400, y: 160 },
          { x: 600, y: 400 },
        ]),
      ),
    ).toBeNull();
  });
});

describe("describeTriangle", () => {
  it("reports length, height, area, and circumdiameter for a 3-4-5 triangle", () => {
    // Math: (0,0), (4,0), (0,3) → screen origin 400,300 with unit 40
    const info = describeTriangle(
      {
        vertices: [
          { x: 400, y: 300 },
          { x: 560, y: 300 },
          { x: 400, y: 180 },
        ],
        rms: 1,
      },
      VIEW,
    );
    expect(info.length).toBeCloseTo(5);
    expect(info.height).toBeCloseTo(2.4);
    expect(info.area).toBeCloseTo(6);
    expect(info.diameter).toBeCloseTo(5);
    expect(info.overlay[0]).toContain("length = 5");
    expect(info.overlay[1]).toContain("A = 6");
    expect(info.overlay[1]).toContain("d = 5");
  });
});

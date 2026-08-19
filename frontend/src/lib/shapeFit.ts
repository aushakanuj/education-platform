/** Fit a freehand stroke to a circle or triangle with Cartesian measurements. */

import {
  formatCoeff,
  GRID_UNIT,
  screenToMath,
  type ScreenPoint,
  type ViewportOrigin,
} from "./lineEquation";

export type FittedCircle = {
  center: ScreenPoint;
  radius: number;
  rms: number;
};

export type FittedTriangle = {
  vertices: [ScreenPoint, ScreenPoint, ScreenPoint];
  rms: number;
};

export type CircleAnalysis = {
  radius: number;
  diameter: number;
  area: number;
  equation: string;
  overlay: string[];
};

export type TriangleAnalysis = {
  length: number;
  height: number;
  area: number;
  diameter: number;
  overlay: string[];
};

const MIN_RADIUS_PX = 24;
const MIN_TRIANGLE_SIDE_PX = 36;
const MIN_CIRCLE_SPAN = (Math.PI * 2 * 200) / 360;
const MAX_PATH_TO_CIRCUMFERENCE = 2.8;
const MIN_PATH_TO_CIRCUMFERENCE = 0.4;
const MAX_TRIANGLE_RMS_RATIO = 0.14;
const MIN_TRIANGLE_AREA_PX = 420;
const CLOSE_GAP_RATIO = 0.22;
const CLOSE_GAP_PX = 48;
const LOOP_GAP_RATIO = 0.35;
const LOOP_GAP_PX = 80;

function dist(a: ScreenPoint, b: ScreenPoint): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function pathLength(points: ScreenPoint[]): number {
  let length = 0;
  for (let i = 1; i < points.length; i += 1) {
    length += dist(points[i - 1]!, points[i]!);
  }
  return length;
}

function meanSide(vertices: [ScreenPoint, ScreenPoint, ScreenPoint]): number {
  return (
    (dist(vertices[0], vertices[1]) +
      dist(vertices[1], vertices[2]) +
      dist(vertices[2], vertices[0])) /
    3
  );
}

function angularSpan(points: ScreenPoint[], center: ScreenPoint): number {
  const angles = points.map((point) => Math.atan2(point.y - center.y, point.x - center.x));
  const sorted = [...angles].sort((left, right) => left - right);
  let largestGap = 0;
  for (let i = 1; i < sorted.length; i += 1) {
    largestGap = Math.max(largestGap, sorted[i]! - sorted[i - 1]!);
  }
  largestGap = Math.max(largestGap, sorted[0]! + Math.PI * 2 - sorted[sorted.length - 1]!);
  return Math.PI * 2 - largestGap;
}

function isClosedStroke(points: ScreenPoint[]): boolean {
  const length = pathLength(points);
  if (length < 1) return false;
  return dist(points[0]!, points[points.length - 1]!) <= Math.max(CLOSE_GAP_PX, length * CLOSE_GAP_RATIO);
}

function isClosedLoop(points: ScreenPoint[]): boolean {
  const length = pathLength(points);
  if (length < 1) return false;
  return dist(points[0]!, points[points.length - 1]!) <= Math.max(LOOP_GAP_PX, length * LOOP_GAP_RATIO);
}

function closedLoop(points: ScreenPoint[]): ScreenPoint[] {
  if (points.length < 2) return points;
  const loop = dist(points[0]!, points[points.length - 1]!) < 8 ? points.slice(0, -1) : [...points];
  return loop;
}

function resamplePolyline(points: ScreenPoint[], spacing: number): ScreenPoint[] {
  if (points.length < 2) return points.map((point) => ({ ...point }));
  const out: ScreenPoint[] = [{ ...points[0]! }];
  let remaining = spacing;
  for (let i = 1; i < points.length; i += 1) {
    let x0 = points[i - 1]!.x;
    let y0 = points[i - 1]!.y;
    const x1 = points[i]!.x;
    const y1 = points[i]!.y;
    let segLen = Math.hypot(x1 - x0, y1 - y0);
    if (segLen < 1e-6) continue;
    while (segLen >= remaining) {
      const t = remaining / segLen;
      x0 += (x1 - x0) * t;
      y0 += (y1 - y0) * t;
      out.push({ x: x0, y: y0 });
      segLen = Math.hypot(x1 - x0, y1 - y0);
      remaining = spacing;
    }
    remaining -= segLen;
  }
  const last = points[points.length - 1]!;
  if (dist(out[out.length - 1]!, last) > 0.5) out.push({ ...last });
  return out;
}

function pointToSegmentDistance(point: ScreenPoint, a: ScreenPoint, b: ScreenPoint): number {
  const abx = b.x - a.x;
  const aby = b.y - a.y;
  const lenSq = abx * abx + aby * aby;
  if (lenSq < 1e-6) return dist(point, a);
  const t = Math.max(0, Math.min(1, ((point.x - a.x) * abx + (point.y - a.y) * aby) / lenSq));
  return Math.hypot(point.x - (a.x + abx * t), point.y - (a.y + aby * t));
}

function triangleArea(a: ScreenPoint, b: ScreenPoint, c: ScreenPoint): number {
  return Math.abs((a.x * (b.y - c.y) + b.x * (c.y - a.y) + c.x * (a.y - b.y)) / 2);
}

function cross(origin: ScreenPoint, a: ScreenPoint, b: ScreenPoint): number {
  return (a.x - origin.x) * (b.y - origin.y) - (a.y - origin.y) * (b.x - origin.x);
}

function convexHull(points: ScreenPoint[]): ScreenPoint[] {
  const sorted = [...points].sort((left, right) => left.x - right.x || left.y - right.y);
  const unique: ScreenPoint[] = [];
  for (const point of sorted) {
    const prev = unique[unique.length - 1];
    if (prev && dist(prev, point) < 0.5) continue;
    unique.push(point);
  }
  if (unique.length < 3) return unique;

  const lower: ScreenPoint[] = [];
  for (const point of unique) {
    while (lower.length >= 2 && cross(lower[lower.length - 2]!, lower[lower.length - 1]!, point) <= 0) {
      lower.pop();
    }
    lower.push(point);
  }
  const upper: ScreenPoint[] = [];
  for (let i = unique.length - 1; i >= 0; i -= 1) {
    const point = unique[i]!;
    while (upper.length >= 2 && cross(upper[upper.length - 2]!, upper[upper.length - 1]!, point) <= 0) {
      upper.pop();
    }
    upper.push(point);
  }
  lower.pop();
  upper.pop();
  return [...lower, ...upper];
}

function maxAreaTriangle(hull: ScreenPoint[]): [ScreenPoint, ScreenPoint, ScreenPoint] | null {
  if (hull.length < 3) return null;
  let best: [ScreenPoint, ScreenPoint, ScreenPoint] | null = null;
  let bestArea = 0;
  for (let i = 0; i < hull.length; i += 1) {
    for (let j = i + 1; j < hull.length; j += 1) {
      for (let k = j + 1; k < hull.length; k += 1) {
        const area = triangleArea(hull[i]!, hull[j]!, hull[k]!);
        if (area > bestArea) {
          bestArea = area;
          best = [hull[i]!, hull[j]!, hull[k]!];
        }
      }
    }
  }
  return best;
}

function turningPeaks(points: ScreenPoint[]): number[] {
  const n = points.length;
  if (n < 8) return [];
  const window = Math.max(2, Math.round(n * 0.04));
  const scores: number[] = new Array(n).fill(0);
  for (let i = 0; i < n; i += 1) {
    const prev = points[(i - window + n) % n]!;
    const cur = points[i]!;
    const next = points[(i + window) % n]!;
    const v1x = cur.x - prev.x;
    const v1y = cur.y - prev.y;
    const v2x = next.x - cur.x;
    const v2y = next.y - cur.y;
    const l1 = Math.hypot(v1x, v1y);
    const l2 = Math.hypot(v2x, v2y);
    if (l1 < 1e-6 || l2 < 1e-6) continue;
    const cr = v1x * v2y - v1y * v2x;
    const dot = v1x * v2x + v1y * v2y;
    scores[i] = Math.abs(Math.atan2(cr, dot));
  }

  const minScore = (32 * Math.PI) / 180;
  const minSep = Math.max(4, Math.round(n * 0.12));
  const order = scores
    .map((score, index) => ({ score, index }))
    .filter((item) => item.score >= minScore)
    .sort((left, right) => right.score - left.score);

  const peaks: number[] = [];
  for (const item of order) {
    if (peaks.some((peak) => Math.min(Math.abs(peak - item.index), n - Math.abs(peak - item.index)) < minSep)) {
      continue;
    }
    peaks.push(item.index);
    if (peaks.length === 3) break;
  }
  return peaks.sort((left, right) => left - right);
}

function edgeResiduals(
  points: ScreenPoint[],
  vertices: [ScreenPoint, ScreenPoint, ScreenPoint],
): { rms: number; covered: boolean } {
  const edges: Array<[ScreenPoint, ScreenPoint]> = [
    [vertices[0], vertices[1]],
    [vertices[1], vertices[2]],
    [vertices[2], vertices[0]],
  ];
  let residualSq = 0;
  const hits = [0, 0, 0];
  for (const point of points) {
    let best = Infinity;
    let bestEdge = 0;
    for (let i = 0; i < 3; i += 1) {
      const d = pointToSegmentDistance(point, edges[i]![0], edges[i]![1]);
      if (d < best) {
        best = d;
        bestEdge = i;
      }
    }
    residualSq += best * best;
    hits[bestEdge] += 1;
  }
  const minHits = Math.max(3, Math.floor(points.length * 0.12));
  return {
    rms: Math.sqrt(residualSq / points.length),
    covered: hits.every((count) => count >= minHits),
  };
}

export function fitCircle(points: ScreenPoint[]): FittedCircle | null {
  if (points.length < 8) return null;
  if (!isClosedLoop(points)) return null;

  const loop = closedLoop(points);
  let cx = 0;
  let cy = 0;
  for (const point of loop) {
    cx += point.x;
    cy += point.y;
  }
  cx /= loop.length;
  cy /= loop.length;
  const center = { x: cx, y: cy };

  if (angularSpan(loop, center) < MIN_CIRCLE_SPAN) return null;

  let radiusSum = 0;
  for (const point of loop) {
    radiusSum += dist(point, center);
  }
  const radius = radiusSum / loop.length;
  if (radius < MIN_RADIUS_PX) return null;

  const gap = dist(points[0]!, points[points.length - 1]!);
  if (gap > Math.max(56, radius * 0.95)) return null;

  let residualSq = 0;
  for (const point of loop) {
    const err = dist(point, center) - radius;
    residualSq += err * err;
  }

  const length = pathLength(points);
  const circumference = Math.PI * 2 * radius;
  if (length > circumference * MAX_PATH_TO_CIRCUMFERENCE) return null;
  if (length < circumference * MIN_PATH_TO_CIRCUMFERENCE) return null;

  return { center, radius, rms: Math.sqrt(residualSq / loop.length) };
}

export function fitTriangle(points: ScreenPoint[]): FittedTriangle | null {
  if (points.length < 12) return null;
  if (!isClosedStroke(points)) return null;

  const loop = closedLoop(points);
  const sampled = resamplePolyline([...loop, loop[0]!], 4);
  const body = closedLoop(sampled);
  if (body.length < 10) return null;

  let vertices: [ScreenPoint, ScreenPoint, ScreenPoint] | null = null;
  const peaks = turningPeaks(body);
  if (peaks.length === 3) {
    vertices = [body[peaks[0]!]!, body[peaks[1]!]!, body[peaks[2]!]!];
  } else {
    const hull = convexHull(body);
    if (hull.length >= 3 && hull.length <= 6) {
      vertices = maxAreaTriangle(hull);
    }
  }
  if (!vertices) return null;

  const sides = [
    dist(vertices[0], vertices[1]),
    dist(vertices[1], vertices[2]),
    dist(vertices[2], vertices[0]),
  ];
  if (sides.some((side) => side < MIN_TRIANGLE_SIDE_PX)) return null;
  const area = triangleArea(vertices[0], vertices[1], vertices[2]);
  if (area < MIN_TRIANGLE_AREA_PX) return null;

  const { rms, covered } = edgeResiduals(body, vertices);
  if (!covered) return null;
  if (rms / meanSide(vertices) > MAX_TRIANGLE_RMS_RATIO) return null;

  return { vertices, rms };
}

function centeredSquare(variable: string, offset: number): string {
  const snapped = Number(offset.toFixed(2));
  if (Math.abs(snapped) < 0.05) return `${variable}²`;
  const sign = snapped > 0 ? "-" : "+";
  return `(${variable} ${sign} ${formatCoeff(Math.abs(snapped))})²`;
}

export function describeCircle(circle: FittedCircle, view: ViewportOrigin): CircleAnalysis {
  const unit = view.unit ?? GRID_UNIT;
  const center = screenToMath(circle.center, view);
  const radius = circle.radius / unit;
  const diameter = radius * 2;
  const area = Math.PI * radius * radius;
  const rDisplay = Number(radius.toFixed(2));
  const equation = `${centeredSquare("x", center.x)} + ${centeredSquare("y", center.y)} = ${formatCoeff(rDisplay * rDisplay)}`;
  return {
    radius,
    diameter,
    area,
    equation,
    overlay: [
      equation,
      `r = ${formatCoeff(radius)}    d = ${formatCoeff(diameter)}`,
      `A ≈ ${formatCoeff(area)}`,
    ],
  };
}

export function longestSideIndex(vertices: [ScreenPoint, ScreenPoint, ScreenPoint]): number {
  const sides = [
    dist(vertices[1], vertices[2]),
    dist(vertices[2], vertices[0]),
    dist(vertices[0], vertices[1]),
  ];
  let index = 0;
  if (sides[1]! > sides[index]!) index = 1;
  if (sides[2]! > sides[index]!) index = 2;
  return index;
}

export function altitudeFoot(
  vertex: ScreenPoint,
  a: ScreenPoint,
  b: ScreenPoint,
): { foot: ScreenPoint; onSegment: boolean } {
  const abx = b.x - a.x;
  const aby = b.y - a.y;
  const lenSq = abx * abx + aby * aby;
  if (lenSq < 1e-6) return { foot: { ...a }, onSegment: true };
  const t = ((vertex.x - a.x) * abx + (vertex.y - a.y) * aby) / lenSq;
  return {
    foot: { x: a.x + abx * t, y: a.y + aby * t },
    onSegment: t >= 0 && t <= 1,
  };
}

export function describeTriangle(
  triangle: FittedTriangle,
  view: ViewportOrigin,
): TriangleAnalysis {
  const unit = view.unit ?? GRID_UNIT;
  const [a, b, c] = triangle.vertices;
  const sideA = dist(b, c) / unit;
  const sideB = dist(c, a) / unit;
  const sideC = dist(a, b) / unit;
  const length = Math.max(sideA, sideB, sideC);
  const areaPx = triangleArea(a, b, c);
  const area = areaPx / (unit * unit);
  const height = length > 1e-6 ? (2 * area) / length : 0;
  const diameter = area > 1e-6 ? (sideA * sideB * sideC) / (2 * area) : 0;
  return {
    length,
    height,
    area,
    diameter,
    overlay: [
      `length = ${formatCoeff(length)}    h = ${formatCoeff(height)}`,
      `A = ${formatCoeff(area)}    d = ${formatCoeff(diameter)}`,
    ],
  };
}

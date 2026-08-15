/** Fit a freehand stroke to a Cartesian line with origin at the canvas center. */

export const GRID_UNIT = 40;

export type ScreenPoint = { x: number; y: number };

export type FittedSegment = {
  start: ScreenPoint;
  end: ScreenPoint;
};

export type ViewportOrigin = {
  width: number;
  height: number;
  unit?: number;
};

export type LineAnalysis = {
  equation: string;
  slope: number | null;
  slopeLabel: string;
  angleDeg: number | null;
  yIntercept: number | null;
  xIntercept: number | null;
  overlay: string[];
};

const MIN_LENGTH_PX = 48;
const MAX_RMS_RATIO = 0.1;
const MAX_PATH_TO_CHORD = 1.35;
const DISPLAY_SNAP = 0.05;
const STEEP_SLOPE = 50;

export function screenToMath(
  point: ScreenPoint,
  view: ViewportOrigin,
): { x: number; y: number } {
  const unit = view.unit ?? GRID_UNIT;
  return {
    x: (point.x - view.width / 2) / unit,
    y: (view.height / 2 - point.y) / unit,
  };
}

export function formatCoeff(value: number, digits = 2): string {
  const rounded = Number(value.toFixed(digits));
  if (Object.is(rounded, -0) || rounded === 0) return "0";
  return String(rounded);
}

export function fitStraightLine(points: ScreenPoint[]): FittedSegment | null {
  if (points.length < 2) return null;

  let cx = 0;
  let cy = 0;
  for (const point of points) {
    cx += point.x;
    cy += point.y;
  }
  cx /= points.length;
  cy /= points.length;

  let cxx = 0;
  let cxy = 0;
  let cyy = 0;
  for (const point of points) {
    const dx = point.x - cx;
    const dy = point.y - cy;
    cxx += dx * dx;
    cxy += dx * dy;
    cyy += dy * dy;
  }

  if (cxx + cyy < 1e-6) return null;

  const theta = 0.5 * Math.atan2(2 * cxy, cxx - cyy);
  const dirX = Math.cos(theta);
  const dirY = Math.sin(theta);

  let tMin = Infinity;
  let tMax = -Infinity;
  let residualSq = 0;
  let pathLen = 0;
  for (let i = 0; i < points.length; i += 1) {
    const point = points[i]!;
    const dx = point.x - cx;
    const dy = point.y - cy;
    const t = dx * dirX + dy * dirY;
    if (t < tMin) tMin = t;
    if (t > tMax) tMax = t;
    const rx = dx - t * dirX;
    const ry = dy - t * dirY;
    residualSq += rx * rx + ry * ry;
    if (i > 0) {
      const prev = points[i - 1]!;
      pathLen += Math.hypot(point.x - prev.x, point.y - prev.y);
    }
  }

  const length = tMax - tMin;
  if (length < MIN_LENGTH_PX) return null;
  const rms = Math.sqrt(residualSq / points.length);
  if (rms / length > MAX_RMS_RATIO) return null;
  if (pathLen > length * MAX_PATH_TO_CHORD) return null;

  return {
    start: { x: cx + dirX * tMin, y: cy + dirY * tMin },
    end: { x: cx + dirX * tMax, y: cy + dirY * tMax },
  };
}

export function clipLineToRect(
  point: ScreenPoint,
  direction: ScreenPoint,
  width: number,
  height: number,
): [ScreenPoint, ScreenPoint] | null {
  const hits: ScreenPoint[] = [];
  const push = (x: number, y: number) => {
    if (x < -0.5 || x > width + 0.5 || y < -0.5 || y > height + 0.5) return;
    if (hits.some((hit) => Math.hypot(hit.x - x, hit.y - y) < 0.5)) return;
    hits.push({ x, y });
  };

  const { x: px, y: py } = point;
  const { x: dx, y: dy } = direction;

  if (Math.abs(dx) > 1e-9) {
    push(0, py + ((0 - px) / dx) * dy);
    push(width, py + ((width - px) / dx) * dy);
  }
  if (Math.abs(dy) > 1e-9) {
    push(px + ((0 - py) / dy) * dx, 0);
    push(px + ((height - py) / dy) * dx, height);
  }

  let best: [ScreenPoint, ScreenPoint] | null = null;
  let bestD = -1;
  for (let i = 0; i < hits.length; i += 1) {
    for (let j = i + 1; j < hits.length; j += 1) {
      const a = hits[i]!;
      const b = hits[j]!;
      const d = Math.hypot(a.x - b.x, a.y - b.y);
      if (d > bestD) {
        bestD = d;
        best = [a, b];
      }
    }
  }
  return best;
}

function snapNear(value: number, target: number): boolean {
  return Math.abs(value - target) < DISPLAY_SNAP;
}

function displaySlope(slope: number): number {
  if (snapNear(slope, 0)) return 0;
  if (snapNear(slope, 1)) return 1;
  if (snapNear(slope, -1)) return -1;
  return slope;
}

function displayIntercept(intercept: number): number {
  return snapNear(intercept, 0) ? 0 : intercept;
}

function slopeTerm(slope: number): string {
  if (slope === 1) return "x";
  if (slope === -1) return "-x";
  return `${formatCoeff(slope)}x`;
}

function interceptTerm(intercept: number): string {
  if (intercept === 0) return "";
  const sign = intercept > 0 ? "+" : "-";
  return ` ${sign} ${formatCoeff(Math.abs(intercept))}`;
}

export function describeLine(
  start: ScreenPoint,
  end: ScreenPoint,
  view: ViewportOrigin,
): LineAnalysis {
  const p1 = screenToMath(start, view);
  const p2 = screenToMath(end, view);
  const dx = p2.x - p1.x;
  const dy = p2.y - p1.y;
  const rawAngle = (Math.atan2(dy, dx) * 180) / Math.PI;
  const angleDeg = Number((((rawAngle % 180) + 270) % 180) - 90);

  if (Math.abs(dx) < 1e-6 || Math.abs(dy / dx) > STEEP_SLOPE) {
    const x = displayIntercept((p1.x + p2.x) / 2);
    const equation = `x = ${formatCoeff(x)}`;
    return {
      equation,
      slope: null,
      slopeLabel: "undefined (vertical)",
      angleDeg: 90,
      yIntercept: null,
      xIntercept: x,
      overlay: [equation, "m undefined (vertical)", "θ = 90°"],
    };
  }

  const slope = displaySlope(dy / dx);
  const yIntercept = displayIntercept(p1.y - (dy / dx) * p1.x);
  const horizontal = slope === 0;
  const equation = horizontal
    ? `y = ${formatCoeff(yIntercept)}`
    : `y = ${slopeTerm(slope)}${interceptTerm(yIntercept)}`;

  const xIntercept = horizontal ? null : displayIntercept(-yIntercept / slope);
  const throughOrigin = yIntercept === 0 && (xIntercept === null || xIntercept === 0);

  const overlay = [
    equation,
    `m = ${formatCoeff(slope)}    θ ≈ ${formatCoeff(angleDeg, 0)}°`,
  ];
  if (throughOrigin) {
    overlay.push("through origin (0, 0)");
  } else if (horizontal) {
    overlay.push(`y-intercept = ${formatCoeff(yIntercept)}`);
  } else {
    overlay.push(
      `x-int = ${formatCoeff(xIntercept!)}    y-int = ${formatCoeff(yIntercept)}`,
    );
  }

  return {
    equation,
    slope,
    slopeLabel: formatCoeff(slope),
    angleDeg,
    yIntercept,
    xIntercept,
    overlay,
  };
}

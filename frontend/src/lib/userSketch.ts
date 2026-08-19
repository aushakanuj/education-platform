/** Portfolio-style canvas sketch: drag on empty space, snap shapes, fade out. */

import {
  clipLineToRect,
  describeLine,
  fitStraightLine,
  GRID_UNIT,
  type FittedSegment,
  type LineAnalysis,
} from "./lineEquation";
import {
  altitudeFoot,
  describeCircle,
  describeTriangle,
  fitCircle,
  fitTriangle,
  longestSideIndex,
  type CircleAnalysis,
  type FittedCircle,
  type FittedTriangle,
  type TriangleAnalysis,
} from "./shapeFit";

export type SketchPoint = { x: number; y: number; t: number };

const VANISH_MS = 15000;
const STROKE = "28, 42, 34";
const ACCENT = "63, 111, 90";
const INTERACTIVE_SELECTOR = [
  "a",
  "button",
  "input",
  "textarea",
  "select",
  "summary",
  "label",
  "[role='button']",
  "[role='link']",
  ".card",
  ".rail",
  ".btn",
  ".crumbs",
  ".topbar",
].join(",");

type FittedShape =
  | { type: "line"; segment: FittedSegment; analysis: LineAnalysis }
  | { type: "circle"; circle: FittedCircle; analysis: CircleAnalysis }
  | { type: "triangle"; triangle: FittedTriangle; analysis: TriangleAnalysis };

type Stroke = {
  points: SketchPoint[];
  fitted: FittedShape | null;
};

export function canStartSketch(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  return !target.closest(INTERACTIVE_SELECTOR);
}

function smoothPath(points: SketchPoint[]): SketchPoint[] {
  if (points.length < 3) return points;

  let smoothed = [...points];
  const passes: { window: number; weight: "linear" | "gaussian" }[] = [
    { window: 2, weight: "linear" },
    { window: 3, weight: "gaussian" },
    { window: 4, weight: "gaussian" },
    { window: 3, weight: "gaussian" },
  ];

  for (const pass of passes) {
    const next: SketchPoint[] = [];
    const w = pass.window;
    for (let i = 0; i < smoothed.length; i += 1) {
      let sumX = 0;
      let sumY = 0;
      let weightSum = 0;
      for (let j = -w; j <= w; j += 1) {
        const idx = i + j;
        if (idx < 0 || idx >= smoothed.length) continue;
        const weight =
          pass.weight === "gaussian"
            ? Math.exp(-(j * j) / (2 * w))
            : 1 - Math.abs(j) / (w + 1);
        sumX += smoothed[idx]!.x * weight;
        sumY += smoothed[idx]!.y * weight;
        weightSum += weight;
      }
      next.push({
        x: sumX / weightSum,
        y: sumY / weightSum,
        t: smoothed[i]!.t,
      });
    }
    smoothed = next;
  }

  return smoothed;
}

function strokeOpacity(now: number, startedAt: number): number {
  const age = now - startedAt;
  if (age >= VANISH_MS) return 0;
  return Math.max(0, (1 - age / VANISH_MS) * 0.6);
}

function drawAxes(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  opacity: number,
): void {
  const ox = width / 2;
  const oy = height / 2;
  const alpha = opacity * 0.85;
  ctx.save();
  ctx.strokeStyle = `rgba(${ACCENT}, ${alpha})`;
  ctx.fillStyle = `rgba(${ACCENT}, ${Math.min(1, alpha + 0.15)})`;
  ctx.lineWidth = 1.25;
  ctx.setLineDash([]);

  ctx.beginPath();
  ctx.moveTo(12, oy);
  ctx.lineTo(width - 12, oy);
  ctx.moveTo(ox, height - 12);
  ctx.lineTo(ox, 12);
  ctx.stroke();

  ctx.beginPath();
  ctx.moveTo(width - 12, oy);
  ctx.lineTo(width - 22, oy - 5);
  ctx.moveTo(width - 12, oy);
  ctx.lineTo(width - 22, oy + 5);
  ctx.moveTo(ox, 12);
  ctx.lineTo(ox - 5, 22);
  ctx.moveTo(ox, 12);
  ctx.lineTo(ox + 5, 22);
  ctx.stroke();

  ctx.font = "600 12px 'IBM Plex Mono', ui-monospace, monospace";
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  ctx.fillText("x", width - 34, oy + 14);
  ctx.textAlign = "center";
  ctx.fillText("y", ox + 14, 28);
  ctx.textAlign = "right";
  ctx.fillText("(0, 0)", ox - 8, oy + 16);
  ctx.restore();
}

function overlaySize(ctx: CanvasRenderingContext2D, rows: string[]): { boxW: number; boxH: number } {
  const padX = 10;
  const padY = 8;
  const lineHeight = 16;
  const textW = Math.max(...rows.map((row) => ctx.measureText(row).width), 80);
  return { boxW: textW + padX * 2, boxH: rows.length * lineHeight + padY * 2 };
}

function drawOverlayBox(
  ctx: CanvasRenderingContext2D,
  rows: string[],
  box: { x: number; y: number },
  boxW: number,
  boxH: number,
  opacity: number,
): void {
  const padX = 10;
  const padY = 8;
  const lineHeight = 16;
  ctx.fillStyle = `rgba(244, 246, 243, ${Math.min(0.92, opacity + 0.35)})`;
  ctx.strokeStyle = `rgba(${ACCENT}, ${opacity * 0.7})`;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.fillRect(box.x, box.y, boxW, boxH);
  ctx.strokeRect(box.x, box.y, boxW, boxH);

  ctx.font = "600 12px 'IBM Plex Mono', ui-monospace, monospace";
  ctx.textAlign = "left";
  ctx.textBaseline = "top";
  ctx.fillStyle = `rgba(${STROKE}, ${Math.min(1, opacity + 0.35)})`;
  rows.forEach((row, index) => {
    ctx.fillText(row, box.x + padX, box.y + padY + index * lineHeight);
  });
}

function clampBox(
  box: { x: number; y: number },
  boxW: number,
  boxH: number,
  width: number,
  height: number,
): { x: number; y: number } {
  return {
    x: Math.min(Math.max(8, box.x), width - boxW - 8),
    y: Math.min(Math.max(8, box.y), height - boxH - 8),
  };
}

function drawFittedLine(
  ctx: CanvasRenderingContext2D,
  segment: FittedSegment,
  analysis: LineAnalysis,
  width: number,
  height: number,
  opacity: number,
): void {
  const dir = {
    x: segment.end.x - segment.start.x,
    y: segment.end.y - segment.start.y,
  };
  const clipped = clipLineToRect(segment.start, dir, width, height);

  ctx.save();
  if (clipped) {
    ctx.strokeStyle = `rgba(${ACCENT}, ${opacity * 0.55})`;
    ctx.lineWidth = 1;
    ctx.setLineDash([6, 5]);
    ctx.beginPath();
    ctx.moveTo(clipped[0].x, clipped[0].y);
    ctx.lineTo(clipped[1].x, clipped[1].y);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  ctx.strokeStyle = `rgba(${STROKE}, ${opacity})`;
  ctx.lineWidth = 2.5;
  ctx.lineCap = "round";
  ctx.beginPath();
  ctx.moveTo(segment.start.x, segment.start.y);
  ctx.lineTo(segment.end.x, segment.end.y);
  ctx.stroke();

  const midX = (segment.start.x + segment.end.x) / 2;
  const midY = (segment.start.y + segment.end.y) / 2;
  const len = Math.hypot(dir.x, dir.y) || 1;
  const nx = -dir.y / len;
  const ny = dir.x / len;
  const rows = analysis.overlay;
  ctx.font = "600 12px 'IBM Plex Mono', ui-monospace, monospace";
  const { boxW, boxH } = overlaySize(ctx, rows);

  const tryPlace = (sign: number) => ({
    x: midX + nx * 36 * sign - boxW / 2,
    y: midY + ny * 36 * sign - boxH / 2,
  });
  let box = tryPlace(1);
  if (box.x < 8 || box.y < 8 || box.x + boxW > width - 8 || box.y + boxH > height - 8) {
    box = tryPlace(-1);
  }
  drawOverlayBox(ctx, rows, clampBox(box, boxW, boxH, width, height), boxW, boxH, opacity);
  ctx.restore();
}

function drawFittedCircle(
  ctx: CanvasRenderingContext2D,
  circle: FittedCircle,
  analysis: CircleAnalysis,
  width: number,
  height: number,
  opacity: number,
): void {
  const { center, radius } = circle;
  ctx.save();
  ctx.strokeStyle = `rgba(${STROKE}, ${opacity})`;
  ctx.lineWidth = 2.5;
  ctx.lineCap = "round";
  ctx.beginPath();
  ctx.arc(center.x, center.y, radius, 0, Math.PI * 2);
  ctx.stroke();

  ctx.strokeStyle = `rgba(${ACCENT}, ${opacity * 0.7})`;
  ctx.lineWidth = 1;
  ctx.setLineDash([6, 5]);
  ctx.beginPath();
  ctx.moveTo(center.x, center.y);
  ctx.lineTo(center.x + radius, center.y);
  ctx.stroke();
  ctx.setLineDash([]);

  ctx.fillStyle = `rgba(${ACCENT}, ${Math.min(1, opacity + 0.2)})`;
  ctx.beginPath();
  ctx.arc(center.x, center.y, 2.4, 0, Math.PI * 2);
  ctx.fill();

  const rows = analysis.overlay;
  ctx.font = "600 12px 'IBM Plex Mono', ui-monospace, monospace";
  const { boxW, boxH } = overlaySize(ctx, rows);
  const box = clampBox(
    { x: center.x + radius * 0.35, y: center.y - radius - boxH - 8 },
    boxW,
    boxH,
    width,
    height,
  );
  drawOverlayBox(ctx, rows, box, boxW, boxH, opacity);
  ctx.restore();
}

function drawFittedTriangle(
  ctx: CanvasRenderingContext2D,
  triangle: FittedTriangle,
  analysis: TriangleAnalysis,
  width: number,
  height: number,
  opacity: number,
): void {
  const [a, b, c] = triangle.vertices;
  const apexIndex = longestSideIndex(triangle.vertices);
  const apex = triangle.vertices[apexIndex]!;
  const baseA = triangle.vertices[(apexIndex + 1) % 3]!;
  const baseB = triangle.vertices[(apexIndex + 2) % 3]!;
  const { foot, onSegment } = altitudeFoot(apex, baseA, baseB);

  ctx.save();
  ctx.strokeStyle = `rgba(${STROKE}, ${opacity})`;
  ctx.lineWidth = 2.5;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.beginPath();
  ctx.moveTo(a.x, a.y);
  ctx.lineTo(b.x, b.y);
  ctx.lineTo(c.x, c.y);
  ctx.closePath();
  ctx.stroke();

  ctx.strokeStyle = `rgba(${ACCENT}, ${opacity * 0.7})`;
  ctx.lineWidth = 1;
  ctx.setLineDash([6, 5]);
  ctx.beginPath();
  ctx.moveTo(apex.x, apex.y);
  ctx.lineTo(foot.x, foot.y);
  ctx.stroke();
  ctx.setLineDash([]);

  if (onSegment) {
    const dx = baseB.x - baseA.x;
    const dy = baseB.y - baseA.y;
    const len = Math.hypot(dx, dy) || 1;
    const ux = dx / len;
    const uy = dy / len;
    const hx = apex.x - foot.x;
    const hy = apex.y - foot.y;
    const hLen = Math.hypot(hx, hy) || 1;
    const nx = hx / hLen;
    const ny = hy / hLen;
    const mark = 8;
    ctx.strokeStyle = `rgba(${ACCENT}, ${opacity * 0.8})`;
    ctx.beginPath();
    ctx.moveTo(foot.x + ux * mark, foot.y + uy * mark);
    ctx.lineTo(foot.x + ux * mark + nx * mark, foot.y + uy * mark + ny * mark);
    ctx.lineTo(foot.x + nx * mark, foot.y + ny * mark);
    ctx.stroke();
  }

  const cx = (a.x + b.x + c.x) / 3;
  const cy = (a.y + b.y + c.y) / 3;
  const rows = analysis.overlay;
  ctx.font = "600 12px 'IBM Plex Mono', ui-monospace, monospace";
  const { boxW, boxH } = overlaySize(ctx, rows);
  const box = clampBox({ x: cx + 18, y: cy - boxH - 12 }, boxW, boxH, width, height);
  drawOverlayBox(ctx, rows, box, boxW, boxH, opacity);
  ctx.restore();
}

function drawFreehand(ctx: CanvasRenderingContext2D, drawing: SketchPoint[], opacity: number): void {
  if (drawing.length > 1) {
    ctx.strokeStyle = `rgba(${STROKE}, ${opacity})`;
    ctx.beginPath();
    ctx.moveTo(drawing[0]!.x, drawing[0]!.y);
    for (let j = 1; j < drawing.length - 1; j += 1) {
      const p1 = drawing[j]!;
      const p2 = drawing[j + 1]!;
      ctx.quadraticCurveTo(p1.x, p1.y, (p1.x + p2.x) / 2, (p1.y + p2.y) / 2);
    }
    const last = drawing[drawing.length - 1]!;
    ctx.lineTo(last.x, last.y);
    ctx.stroke();
    return;
  }
  if (drawing.length === 1) {
    const p0 = drawing[0]!;
    ctx.fillStyle = `rgba(${STROKE}, ${opacity})`;
    ctx.beginPath();
    ctx.arc(p0.x, p0.y, 0.75, 0, Math.PI * 2);
    ctx.fill();
  }
}

export type UserSketch = {
  begin: (x: number, y: number, now?: number) => void;
  extend: (x: number, y: number, now?: number) => void;
  end: (x: number, y: number, now?: number) => void;
  tick: (ctx: CanvasRenderingContext2D, now: number) => void;
  resize: (width: number, height: number) => void;
  dispose: () => void;
  isDrawing: () => boolean;
};

export function createUserSketch(): UserSketch {
  const strokes: Stroke[] = [];
  let current: Stroke | null = null;
  let width = 0;
  let height = 0;

  const begin = (x: number, y: number, now = Date.now()) => {
    current = {
      points: [{ x, y, t: now }],
      fitted: null,
    };
    strokes.push(current);
  };

  const extend = (x: number, y: number, now = Date.now()) => {
    if (!current) return;
    current.points.push({ x, y, t: now });
  };

  const end = (x: number, y: number, now = Date.now()) => {
    if (!current) return;
    current.points.push({ x, y, t: now });
    const startedAt = current.points[0]!.t;
    const view = { width, height, unit: GRID_UNIT };
    const lineFit = fitStraightLine(current.points);
    if (lineFit && width > 0 && height > 0) {
      current.fitted = {
        type: "line",
        segment: lineFit,
        analysis: describeLine(lineFit.start, lineFit.end, view),
      };
      current.points = [
        { x: lineFit.start.x, y: lineFit.start.y, t: startedAt },
        { x: lineFit.end.x, y: lineFit.end.y, t: now },
      ];
    } else if (width > 0 && height > 0) {
      const triangleFit = fitTriangle(current.points);
      const circleFit = triangleFit ? null : fitCircle(current.points);
      if (triangleFit) {
        current.fitted = {
          type: "triangle",
          triangle: triangleFit,
          analysis: describeTriangle(triangleFit, view),
        };
        const [a, b, c] = triangleFit.vertices;
        current.points = [{ x: (a.x + b.x + c.x) / 3, y: (a.y + b.y + c.y) / 3, t: startedAt }];
      } else if (circleFit) {
        current.fitted = {
          type: "circle",
          circle: circleFit,
          analysis: describeCircle(circleFit, view),
        };
        current.points = [{ x: circleFit.center.x, y: circleFit.center.y, t: startedAt }];
      } else {
        current.points = smoothPath(current.points);
      }
    } else {
      current.points = smoothPath(current.points);
    }
    current = null;
  };

  const tick = (ctx: CanvasRenderingContext2D, now: number) => {
    ctx.save();
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.lineWidth = 2.5;

    let axesOpacity = current ? 0.45 : 0;
    for (const drawing of strokes) {
      if (!drawing.fitted) continue;
      const startedAt = drawing.points[0]?.t ?? now;
      axesOpacity = Math.max(axesOpacity, strokeOpacity(now, startedAt));
    }
    if (axesOpacity > 0 && width > 0 && height > 0) {
      drawAxes(ctx, width, height, axesOpacity);
    }

    for (let i = strokes.length - 1; i >= 0; i -= 1) {
      const drawing = strokes[i]!;
      const startedAt = drawing.points[0]?.t ?? now;
      const opacity = strokeOpacity(now, startedAt);
      if (opacity <= 0 && drawing !== current) {
        strokes.splice(i, 1);
        continue;
      }

      if (drawing.fitted?.type === "line") {
        drawFittedLine(ctx, drawing.fitted.segment, drawing.fitted.analysis, width, height, opacity);
      } else if (drawing.fitted?.type === "circle") {
        drawFittedCircle(ctx, drawing.fitted.circle, drawing.fitted.analysis, width, height, opacity);
      } else if (drawing.fitted?.type === "triangle") {
        drawFittedTriangle(ctx, drawing.fitted.triangle, drawing.fitted.analysis, width, height, opacity);
      } else {
        drawFreehand(ctx, drawing.points, opacity);
      }
    }

    ctx.restore();
  };

  const dispose = () => {
    strokes.length = 0;
    current = null;
  };

  return {
    begin,
    extend,
    end,
    tick,
    resize: (nextW, nextH) => {
      width = nextW;
      height = nextH;
    },
    dispose,
    isDrawing: () => current !== null,
  };
}

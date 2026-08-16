/** Portfolio-style sketch choreography for the ambient backdrop (education-themed). */

export type LineStep = {
  type: "line";
  start: [number, number];
  end: [number, number];
  duration: number;
  weight?: number;
  opacity?: number;
  delay?: number;
  dash?: number[];
};

export type ArcStep = {
  type: "arc";
  center: [number, number];
  radius: number;
  startAngle: number;
  endAngle: number;
  duration: number;
  weight?: number;
  opacity?: number;
  delay?: number;
};

export type TextStep = {
  type: "text";
  point: [number, number];
  text: string;
  delay?: number;
  duration?: number;
  opacity?: number;
};

export type VignetteStep = LineStep | ArcStep | TextStep;

export type VignetteKey =
  | "openBook"
  | "pencil"
  | "atom"
  | "geometry"
  | "flask"
  | "lightbulb"
  | "abacus"
  | "globe";

const GRID_SIZE = 40;
const VANISH_TIME = 15000;
const HOLD_MS = 3000;
const DRAWING_COLOR = "rgba(63, 111, 90, 0.16)";
const STROKE_COLOR = "rgba(28, 42, 34, 0.55)";
const TEXT_COLOR = "rgba(93, 111, 100, 0.55)";

export const VIGNETTES: Record<VignetteKey, VignetteStep[]> = {
  openBook: [
    { type: "line", start: [70, 20], end: [70, 85], duration: 350, weight: 1.4, opacity: 0.18 },
    { type: "line", start: [70, 20], end: [20, 30], duration: 350, weight: 1.3, opacity: 0.16, delay: 250 },
    { type: "line", start: [20, 30], end: [20, 90], duration: 300, weight: 1.3, opacity: 0.16, delay: 500 },
    { type: "line", start: [20, 90], end: [70, 85], duration: 300, weight: 1.3, opacity: 0.16, delay: 750 },
    { type: "line", start: [70, 20], end: [120, 30], duration: 350, weight: 1.3, opacity: 0.16, delay: 350 },
    { type: "line", start: [120, 30], end: [120, 90], duration: 300, weight: 1.3, opacity: 0.16, delay: 650 },
    { type: "line", start: [120, 90], end: [70, 85], duration: 300, weight: 1.3, opacity: 0.16, delay: 900 },
    { type: "line", start: [30, 45], end: [55, 42], duration: 200, weight: 0.8, opacity: 0.1, delay: 1100 },
    { type: "line", start: [30, 55], end: [55, 52], duration: 200, weight: 0.8, opacity: 0.1, delay: 1250 },
    { type: "line", start: [30, 65], end: [55, 62], duration: 200, weight: 0.8, opacity: 0.1, delay: 1400 },
    { type: "line", start: [85, 45], end: [110, 48], duration: 200, weight: 0.8, opacity: 0.1, delay: 1200 },
    { type: "line", start: [85, 55], end: [110, 58], duration: 200, weight: 0.8, opacity: 0.1, delay: 1350 },
    { type: "text", point: [48, 12], text: "Lesson", delay: 1600 },
  ],
  pencil: [
    { type: "line", start: [25, 75], end: [105, 25], duration: 450, weight: 1.6, opacity: 0.18 },
    { type: "line", start: [20, 70], end: [100, 20], duration: 450, weight: 1.6, opacity: 0.18, delay: 80 },
    { type: "line", start: [25, 75], end: [20, 70], duration: 180, weight: 1.2, opacity: 0.14, delay: 450 },
    { type: "line", start: [105, 25], end: [100, 20], duration: 180, weight: 1.2, opacity: 0.14, delay: 500 },
    { type: "line", start: [25, 75], end: [15, 85], duration: 220, weight: 1.1, opacity: 0.14, delay: 650 },
    { type: "line", start: [20, 70], end: [15, 85], duration: 220, weight: 1.1, opacity: 0.14, delay: 750 },
    { type: "line", start: [85, 32], end: [80, 38], duration: 150, weight: 0.9, opacity: 0.12, delay: 900, dash: [3, 3] },
    { type: "text", point: [40, 95], text: "Draft", delay: 1200 },
  ],
  atom: [
    { type: "arc", center: [70, 55], radius: 6, startAngle: 0, endAngle: Math.PI * 2, duration: 250, weight: 1.4, opacity: 0.18 },
    { type: "arc", center: [70, 55], radius: 28, startAngle: 0, endAngle: Math.PI * 2, duration: 500, weight: 1.1, opacity: 0.14, delay: 200 },
    { type: "arc", center: [70, 55], radius: 28, startAngle: 0.6, endAngle: Math.PI * 2 + 0.6, duration: 500, weight: 1.1, opacity: 0.12, delay: 450 },
    { type: "arc", center: [70, 55], radius: 28, startAngle: 1.4, endAngle: Math.PI * 2 + 1.4, duration: 500, weight: 1.1, opacity: 0.12, delay: 700 },
    { type: "arc", center: [98, 55], radius: 3, startAngle: 0, endAngle: Math.PI * 2, duration: 150, weight: 1, opacity: 0.14, delay: 1000 },
    { type: "text", point: [48, 12], text: "Science", delay: 1300 },
  ],
  geometry: [
    { type: "line", start: [25, 80], end: [95, 80], duration: 350, weight: 1.4, opacity: 0.16 },
    { type: "line", start: [95, 80], end: [95, 30], duration: 300, weight: 1.4, opacity: 0.16, delay: 250 },
    { type: "line", start: [95, 30], end: [25, 30], duration: 350, weight: 1.4, opacity: 0.16, delay: 500 },
    { type: "line", start: [25, 30], end: [25, 80], duration: 300, weight: 1.4, opacity: 0.16, delay: 750 },
    { type: "line", start: [25, 30], end: [95, 80], duration: 400, weight: 1, opacity: 0.12, delay: 1000, dash: [4, 4] },
    { type: "arc", center: [25, 80], radius: 14, startAngle: -Math.PI / 2, endAngle: 0, duration: 280, weight: 1, opacity: 0.12, delay: 1300 },
    { type: "text", point: [40, 18], text: "Geometry", delay: 1600 },
  ],
  flask: [
    { type: "line", start: [55, 20], end: [55, 45], duration: 280, weight: 1.3, opacity: 0.16 },
    { type: "line", start: [75, 20], end: [75, 45], duration: 280, weight: 1.3, opacity: 0.16, delay: 100 },
    { type: "line", start: [55, 20], end: [75, 20], duration: 200, weight: 1.2, opacity: 0.14, delay: 280 },
    { type: "line", start: [55, 45], end: [35, 85], duration: 320, weight: 1.4, opacity: 0.16, delay: 450 },
    { type: "line", start: [75, 45], end: [95, 85], duration: 320, weight: 1.4, opacity: 0.16, delay: 550 },
    { type: "line", start: [35, 85], end: [95, 85], duration: 320, weight: 1.4, opacity: 0.16, delay: 800 },
    { type: "line", start: [42, 70], end: [88, 70], duration: 250, weight: 0.9, opacity: 0.12, delay: 1050, dash: [3, 3] },
    { type: "text", point: [45, 100], text: "Lab", delay: 1350 },
  ],
  lightbulb: [
    { type: "arc", center: [65, 42], radius: 22, startAngle: 0.35, endAngle: Math.PI - 0.35, duration: 450, weight: 1.4, opacity: 0.16 },
    { type: "line", start: [50, 58], end: [50, 72], duration: 200, weight: 1.2, opacity: 0.14, delay: 400 },
    { type: "line", start: [80, 58], end: [80, 72], duration: 200, weight: 1.2, opacity: 0.14, delay: 450 },
    { type: "line", start: [50, 72], end: [80, 72], duration: 200, weight: 1.2, opacity: 0.14, delay: 600 },
    { type: "line", start: [54, 72], end: [54, 82], duration: 150, weight: 1, opacity: 0.12, delay: 750 },
    { type: "line", start: [76, 72], end: [76, 82], duration: 150, weight: 1, opacity: 0.12, delay: 800 },
    { type: "line", start: [54, 82], end: [76, 82], duration: 150, weight: 1, opacity: 0.12, delay: 900 },
    { type: "line", start: [65, 20], end: [65, 8], duration: 180, weight: 0.9, opacity: 0.12, delay: 1000 },
    { type: "line", start: [48, 28], end: [38, 18], duration: 180, weight: 0.9, opacity: 0.12, delay: 1100 },
    { type: "line", start: [82, 28], end: [92, 18], duration: 180, weight: 0.9, opacity: 0.12, delay: 1200 },
    { type: "text", point: [42, 98], text: "Idea", delay: 1450 },
  ],
  abacus: [
    { type: "line", start: [25, 25], end: [115, 25], duration: 300, weight: 1.4, opacity: 0.16 },
    { type: "line", start: [25, 85], end: [115, 85], duration: 300, weight: 1.4, opacity: 0.16, delay: 150 },
    { type: "line", start: [25, 25], end: [25, 85], duration: 280, weight: 1.3, opacity: 0.15, delay: 300 },
    { type: "line", start: [115, 25], end: [115, 85], duration: 280, weight: 1.3, opacity: 0.15, delay: 400 },
    { type: "line", start: [40, 25], end: [40, 85], duration: 250, weight: 0.9, opacity: 0.12, delay: 550 },
    { type: "line", start: [55, 25], end: [55, 85], duration: 250, weight: 0.9, opacity: 0.12, delay: 650 },
    { type: "line", start: [70, 25], end: [70, 85], duration: 250, weight: 0.9, opacity: 0.12, delay: 750 },
    { type: "line", start: [85, 25], end: [85, 85], duration: 250, weight: 0.9, opacity: 0.12, delay: 850 },
    { type: "line", start: [100, 25], end: [100, 85], duration: 250, weight: 0.9, opacity: 0.12, delay: 950 },
    { type: "arc", center: [40, 40], radius: 5, startAngle: 0, endAngle: Math.PI * 2, duration: 120, weight: 1, opacity: 0.14, delay: 1100 },
    { type: "arc", center: [55, 55], radius: 5, startAngle: 0, endAngle: Math.PI * 2, duration: 120, weight: 1, opacity: 0.14, delay: 1200 },
    { type: "arc", center: [70, 35], radius: 5, startAngle: 0, endAngle: Math.PI * 2, duration: 120, weight: 1, opacity: 0.14, delay: 1300 },
    { type: "text", point: [48, 12], text: "Math", delay: 1550 },
  ],
  globe: [
    { type: "arc", center: [70, 55], radius: 32, startAngle: 0, endAngle: Math.PI * 2, duration: 500, weight: 1.5, opacity: 0.16 },
    { type: "arc", center: [70, 55], radius: 32, startAngle: -0.4, endAngle: Math.PI + 0.4, duration: 400, weight: 1, opacity: 0.12, delay: 350 },
    { type: "line", start: [38, 55], end: [102, 55], duration: 300, weight: 1, opacity: 0.12, delay: 650 },
    { type: "line", start: [70, 23], end: [70, 87], duration: 300, weight: 1, opacity: 0.12, delay: 800 },
    { type: "line", start: [55, 87], end: [85, 87], duration: 200, weight: 1.2, opacity: 0.14, delay: 1050 },
    { type: "line", start: [70, 87], end: [70, 98], duration: 150, weight: 1.1, opacity: 0.14, delay: 1200 },
    { type: "text", point: [42, 12], text: "World", delay: 1450 },
  ],
};

const VIGNETTE_DIMENSIONS: Record<VignetteKey, [number, number]> = {
  openBook: [130, 110],
  pencil: [120, 110],
  atom: [130, 100],
  geometry: [120, 105],
  flask: [120, 115],
  lightbulb: [120, 115],
  abacus: [130, 105],
  globe: [130, 120],
};

type ActiveVignette = {
  key: VignetteKey;
  sequence: VignetteStep[];
  origin: [number, number];
  startTime: number;
};

type RandomStroke = {
  startX: number;
  startY: number;
  endX: number;
  endY: number;
  progress: number;
  speed: number;
};

function easeOutExpo(x: number): number {
  return x === 1 ? 1 : 1 - Math.pow(2, -10 * x);
}

function maxSequenceTime(sequence: VignetteStep[]): number {
  return Math.max(...sequence.map((s) => (s.delay || 0) + (s.duration || (s.type === "text" ? 800 : 0))));
}

export type DoodleEngine = {
  resize: (width: number, height: number) => void;
  tick: (ctx: CanvasRenderingContext2D, now: number) => void;
  dispose: () => void;
};

export function createDoodleEngine(): DoodleEngine {
  let width = 0;
  let height = 0;
  const activeVignettes: ActiveVignette[] = [];
  const activeTypes = new Set<VignetteKey>();
  const drawings: RandomStroke[] = [];
  const timers: number[] = [];

  const overlaps = (x: number, y: number, dim: [number, number]): boolean => {
    const [dimW, dimH] = dim;
    const padding = 40;
    for (const vig of activeVignettes) {
      const [vigX, vigY] = vig.origin;
      const [vigW, vigH] = VIGNETTE_DIMENSIONS[vig.key];
      const overlapX = x < vigX + vigW + padding && x + dimW + padding > vigX;
      const overlapY = y < vigY + vigH + padding && y + dimH + padding > vigY;
      if (overlapX && overlapY) return true;
    }
    return false;
  };

  const spawnVignette = () => {
    if (width < 200 || height < 200) return;
    const keys = Object.keys(VIGNETTES) as VignetteKey[];
    const available = keys.filter((k) => !activeTypes.has(k));
    const pool = available.length > 0 ? available : keys;
    const key = pool[Math.floor(Math.random() * pool.length)]!;
    const dimensions = VIGNETTE_DIMENSIONS[key];
    const [dimW, dimH] = dimensions;

    const safeZones = [
      { xMin: 0.02, xMax: 0.22, yMin: 0.08, yMax: 0.92 },
      { xMin: 0.78, xMax: 0.98, yMin: 0.08, yMax: 0.92 },
      { xMin: 0.22, xMax: 0.78, yMin: 0.04, yMax: 0.14 },
      { xMin: 0.22, xMax: 0.78, yMin: 0.82, yMax: 0.96 },
    ];

    let found = false;
    let spawnX = 0;
    let spawnY = 0;
    for (let attempt = 0; attempt < 28; attempt += 1) {
      const zone = safeZones[Math.floor(Math.random() * safeZones.length)]!;
      spawnX = width * (zone.xMin + Math.random() * (zone.xMax - zone.xMin));
      spawnY = height * (zone.yMin + Math.random() * (zone.yMax - zone.yMin));
      spawnX = Math.max(16, Math.min(spawnX, width - dimW - 16));
      spawnY = Math.max(16, Math.min(spawnY, height - dimH - 16));
      spawnX = Math.floor(spawnX / GRID_SIZE) * GRID_SIZE;
      spawnY = Math.floor(spawnY / GRID_SIZE) * GRID_SIZE;
      if (!overlaps(spawnX, spawnY, dimensions)) {
        found = true;
        break;
      }
    }
    if (!found) return;

    activeTypes.add(key);
    activeVignettes.push({
      key,
      sequence: VIGNETTES[key],
      origin: [spawnX, spawnY],
      startTime: Date.now(),
    });
  };

  const addRandomDrawing = (instant = false) => {
    if (width < 40 || height < 40) return;
    const startX = Math.random() * width;
    const startY = Math.random() * height;
    const angle = Math.random() * Math.PI * 2;
    const length = 18 + Math.random() * 70;
    drawings.push({
      startX,
      startY,
      endX: startX + Math.cos(angle) * length,
      endY: startY + Math.sin(angle) * length,
      progress: instant ? 1 : 0,
      speed: 0.008 + Math.random() * 0.02,
    });
    if (drawings.length > 55) drawings.shift();
  };

  const renderVignettes = (ctx: CanvasRenderingContext2D, now: number) => {
    ctx.lineCap = "round";
    ctx.lineJoin = "round";

    for (let i = activeVignettes.length - 1; i >= 0; i -= 1) {
      const vig = activeVignettes[i]!;
      const age = now - vig.startTime;
      const life = maxSequenceTime(vig.sequence) + HOLD_MS + VANISH_TIME;
      let globalAlpha = 1;
      if (age > maxSequenceTime(vig.sequence) + HOLD_MS) {
        const fadeAge = age - (maxSequenceTime(vig.sequence) + HOLD_MS);
        if (fadeAge > VANISH_TIME || age > life) {
          activeTypes.delete(vig.key);
          activeVignettes.splice(i, 1);
          continue;
        }
        globalAlpha = 1 - fadeAge / VANISH_TIME;
      }

      const [oX, oY] = vig.origin;
      for (const step of vig.sequence) {
        const stepAge = age - (step.delay || 0);
        if (stepAge < 0) continue;
        const stepDuration = step.duration || (step.type === "text" ? 800 : 0);
        const progress = stepDuration ? Math.min(1, stepAge / stepDuration) : 1;
        const eased = easeOutExpo(progress);

        ctx.globalAlpha = globalAlpha * (step.opacity ?? 1);
        ctx.lineWidth = "weight" in step ? (step.weight ?? 1) : 1;
        ctx.strokeStyle = STROKE_COLOR;
        ctx.fillStyle = step.type === "text" ? TEXT_COLOR : STROKE_COLOR;
        ctx.setLineDash("dash" in step && step.dash ? step.dash : []);

        if (step.type === "line") {
          ctx.beginPath();
          ctx.moveTo(oX + step.start[0], oY + step.start[1]);
          ctx.lineTo(
            oX + step.start[0] + (step.end[0] - step.start[0]) * eased,
            oY + step.start[1] + (step.end[1] - step.start[1]) * eased,
          );
          ctx.stroke();
        } else if (step.type === "arc") {
          ctx.beginPath();
          ctx.arc(
            oX + step.center[0],
            oY + step.center[1],
            step.radius,
            step.startAngle,
            step.startAngle + (step.endAngle - step.startAngle) * eased,
          );
          ctx.stroke();
        } else if (step.type === "text" && eased > 0) {
          const chars = Math.floor(step.text.length * eased);
          const visible = step.text.slice(0, chars);
          ctx.font = "500 13px 'Source Sans 3', ui-sans-serif, system-ui, sans-serif";
          ctx.fillStyle = TEXT_COLOR;
          ctx.globalAlpha = globalAlpha * 0.55;
          let x = oX + step.point[0];
          const y = oY + step.point[1];
          for (let c = 0; c < visible.length; c += 1) {
            const ch = visible[c]!;
            ctx.fillText(ch, x + Math.sin(c * 0.5) * 0.4, y + Math.cos(c * 0.7) * 0.4);
            x += ctx.measureText(ch).width * 0.95;
          }
        }
      }
      ctx.globalAlpha = 1;
      ctx.setLineDash([]);
    }
  };

  const renderDrawings = (ctx: CanvasRenderingContext2D) => {
    ctx.lineCap = "round";
    ctx.lineWidth = 1.15;
    ctx.strokeStyle = DRAWING_COLOR;
    ctx.globalAlpha = 1;
    for (const d of drawings) {
      ctx.beginPath();
      ctx.moveTo(d.startX, d.startY);
      ctx.lineTo(
        d.startX + (d.endX - d.startX) * easeOutExpo(d.progress),
        d.startY + (d.endY - d.startY) * easeOutExpo(d.progress),
      );
      ctx.stroke();
      if (d.progress < 1) {
        d.progress = Math.min(1, d.progress + d.speed);
      }
    }
  };

  const resize = (nextW: number, nextH: number) => {
    width = nextW;
    height = nextH;
  };

  const tick = (ctx: CanvasRenderingContext2D, now: number) => {
    renderVignettes(ctx, now);
    renderDrawings(ctx);
  };

  // Kick off ambient activity
  for (let i = 0; i < 3; i += 1) {
    timers.push(window.setTimeout(() => spawnVignette(), i * 350));
  }
  for (let i = 0; i < 12; i += 1) {
    addRandomDrawing(true);
  }
  timers.push(window.setInterval(spawnVignette, 2200));
  timers.push(window.setInterval(() => addRandomDrawing(false), 1600));

  const dispose = () => {
    for (const id of timers) {
      window.clearTimeout(id);
      window.clearInterval(id);
    }
    timers.length = 0;
    activeVignettes.length = 0;
    drawings.length = 0;
    activeTypes.clear();
  };

  return { resize, tick, dispose };
}

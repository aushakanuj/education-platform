import { useSyncExternalStore } from "react";

/** Subject-view progress painted on the ambient canvas. */
export type BackdropChrome = {
  progressPercent: number;
  progressLabel: string;
  statusLabel: string;
  complete: boolean;
};

let chrome: BackdropChrome | null = null;
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) listener();
}

export function setBackdropChrome(next: BackdropChrome | null) {
  chrome = next;
  emit();
}

export function getBackdropChrome(): BackdropChrome | null {
  return chrome;
}

export function subscribeBackdropChrome(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useBackdropChrome(): BackdropChrome | null {
  return useSyncExternalStore(subscribeBackdropChrome, getBackdropChrome, () => null);
}

export const BACKDROP_CHROME_ANCHOR = "data-backdrop-chrome-anchor";

const INK = "rgba(28, 42, 34, 1)";
const TRACK = "rgba(63, 111, 90, 0.14)";
const FILL_OK = "rgba(21, 128, 61, 0.75)";
const FILL_WARN = "rgba(161, 98, 7, 0.72)";
const BADGE_OK_BG = "rgba(240, 253, 244, 0.92)";
const BADGE_WARN_BG = "rgba(254, 252, 232, 0.92)";

function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
) {
  const radius = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + w, y, x + w, y + h, radius);
  ctx.arcTo(x + w, y + h, x, y + h, radius);
  ctx.arcTo(x, y + h, x, y, radius);
  ctx.arcTo(x, y, x + w, y, radius);
  ctx.closePath();
}

/** Paint subject progress into the chrome anchor rect. */
export function drawBackdropChrome(
  ctx: CanvasRenderingContext2D,
  data: BackdropChrome,
  rect: DOMRectReadOnly,
): void {
  if (rect.width < 40 || rect.height < 24) return;

  const barHeight = 8;
  const barLeft = rect.left + 8;
  const barWidth = Math.max(120, rect.width - 16);
  const barTop = rect.top + Math.max(28, (rect.height - barHeight) / 2 + 6);
  const labelY = barTop - 10;

  ctx.save();
  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";
  ctx.font = '500 0.78rem "IBM Plex Mono", ui-monospace, monospace';
  ctx.fillStyle = INK;
  ctx.fillText(data.progressLabel, barLeft, labelY);

  ctx.font = '600 0.72rem "IBM Plex Mono", ui-monospace, monospace';
  const badgeText = data.statusLabel;
  const badgePadX = 10;
  const badgeW = ctx.measureText(badgeText).width + badgePadX * 2;
  const badgeH = 22;
  const badgeX = barLeft + barWidth - badgeW;
  const badgeY = labelY - 15;
  ctx.fillStyle = data.complete ? BADGE_OK_BG : BADGE_WARN_BG;
  roundRect(ctx, badgeX, badgeY, badgeW, badgeH, 999);
  ctx.fill();
  ctx.fillStyle = data.complete ? "rgba(21, 128, 61, 0.95)" : "rgba(161, 98, 7, 0.95)";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(badgeText, badgeX + badgeW / 2, badgeY + badgeH / 2);

  roundRect(ctx, barLeft, barTop, barWidth, barHeight, 4);
  ctx.fillStyle = TRACK;
  ctx.fill();

  const fillW = Math.max(0, Math.min(1, data.progressPercent / 100)) * barWidth;
  if (fillW > 0) {
    roundRect(ctx, barLeft, barTop, fillW, barHeight, 4);
    ctx.fillStyle = data.complete || data.progressPercent >= 100 ? FILL_OK : FILL_WARN;
    ctx.fill();
  }

  ctx.restore();
}

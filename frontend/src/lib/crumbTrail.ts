import { useSyncExternalStore } from "react";

export type Crumb = {
  label: string;
  to?: string;
  onClick?: () => void;
};

let trail: Crumb[] | null = null;
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) listener();
}

function sameTrail(a: Crumb[] | null, b: Crumb[] | null): boolean {
  if (a === b) return true;
  if (!a || !b || a.length !== b.length) return false;
  return a.every(
    (part, index) => part.label === b[index]?.label && part.to === b[index]?.to,
  );
}

export function setCrumbTrail(next: Crumb[] | null): void {
  if (sameTrail(trail, next)) return;
  trail = next;
  emit();
}

export function getCrumbTrail(): Crumb[] | null {
  return trail;
}

export function subscribeCrumbTrail(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useCrumbTrail(): Crumb[] | null {
  return useSyncExternalStore(subscribeCrumbTrail, getCrumbTrail, () => null);
}

import { createContext, useContext, type MutableRefObject, type ReactNode } from "react";
import { createPortal } from "react-dom";

export const RouteChromeSlotContext = createContext<{
  slot: HTMLElement | null;
  enabled: boolean;
}>({ slot: null, enabled: false });

export type ChromeCrumb = { label: string; to?: string };

export type ChromePlayed = { crumb: string; parts: ChromeCrumb[] };

/** Persistent across route fades so Strict Mode remounts do not replay enter animations. */
export const ChromePlayedContext = createContext<MutableRefObject<ChromePlayed> | null>(null);

/** Render page chrome (crumbs) outside the route fade. */
export function PageChrome({ children }: { children: ReactNode }) {
  const { slot, enabled } = useContext(RouteChromeSlotContext);
  if (!enabled) {
    return <div className="page-chrome">{children}</div>;
  }
  if (!slot) return null;
  return createPortal(children, slot);
}

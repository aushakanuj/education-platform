import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useContext, useLayoutEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { ChromePlayedContext, type ChromeCrumb } from "./PageChrome";

export type Crumb = ChromeCrumb;

const TRANSITION = { duration: 0.38, ease: [0.22, 1, 0.36, 1] as const };
const FROM_RIGHT = { x: 56, opacity: 0 };

function initialVisible(
  shouldAnimate: boolean,
  kind: ReturnType<typeof navKind>,
  stored: Crumb[],
  parts: Crumb[],
): Crumb[] {
  if (shouldAnimate && (kind === "back" || kind === "replace") && stored.length > 0) {
    return stored;
  }
  return parts;
}

function trailKey(parts: Crumb[]): string {
  return parts.map((part) => part.label).join("\0");
}

function prefixMatches(short: Crumb[], long: Crumb[]): boolean {
  return short.every((part, index) => part.label === long[index]?.label);
}

function navKind(prev: Crumb[], next: Crumb[]): "forward" | "back" | "replace" | "same" {
  if (trailKey(prev) === trailKey(next)) return "same";
  if (next.length > prev.length && prefixMatches(prev, next)) return "forward";
  if (next.length < prev.length && prefixMatches(next, prev)) return "back";
  return "replace";
}

function firstNewIndex(
  prev: Crumb[],
  next: Crumb[],
  kind: ReturnType<typeof navKind>,
): number {
  if (next.length <= 1 || kind === "back" || kind === "same") return next.length;
  if (prev.length === 0) return Math.max(0, next.length - 1);
  const limit = Math.min(prev.length, next.length);
  for (let i = 0; i < limit; i++) {
    if (prev[i].label !== next[i].label) return i;
  }
  return prev.length;
}

export function Crumbs({ parts }: { parts: Crumb[] }) {
  const reduceMotion = useReducedMotion();
  const location = useLocation();
  const played = useContext(ChromePlayedContext);
  const token = `${location.key}:${trailKey(parts)}`;
  const stored = played?.current.parts ?? [];
  const shouldAnimate = Boolean(played) && played.current.crumb !== token;
  const kind = shouldAnimate ? navKind(stored, parts) : "same";

  const [trailMotion] = useState(() => ({
    kind,
    shouldAnimate,
    firstNew: firstNewIndex(stored, parts, kind),
  }));

  const [visible, setVisible] = useState<Crumb[]>(() =>
    initialVisible(shouldAnimate, kind, stored, parts),
  );

  useLayoutEffect(() => {
    setVisible(parts);
    if (played) {
      played.current.crumb = token;
      played.current.parts = parts.map((part) => ({ ...part }));
    }
  }, [played, token]);

  const animate = trailMotion.shouldAnimate && !reduceMotion;
  const playEnter =
    animate && (trailMotion.kind === "forward" || trailMotion.kind === "replace");

  return (
    <nav className="crumbs" aria-label="Breadcrumb">
      <AnimatePresence initial={playEnter} mode="popLayout">
        {visible.map((part, index) => {
          const isLast = index === visible.length - 1;
          const label =
            part.to && !isLast ? (
              <Link to={part.to}>{part.label}</Link>
            ) : (
              <span aria-current={isLast ? "page" : undefined}>{part.label}</span>
            );
          const enterFromRight = playEnter && index >= trailMotion.firstNew;

          return (
            <motion.span
              key={part.label}
              className={isLast ? "crumbs__item crumbs__item--current" : "crumbs__item"}
              initial={enterFromRight ? FROM_RIGHT : false}
              animate={{ x: 0, opacity: 1 }}
              exit={FROM_RIGHT}
              transition={TRANSITION}
            >
              {index > 0 && (
                <span className="crumbs__sep" aria-hidden="true">
                  /
                </span>
              )}
              {label}
            </motion.span>
          );
        })}
      </AnimatePresence>
    </nav>
  );
}

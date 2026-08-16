import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { createContext, useContext, useLayoutEffect, useRef, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { crumbSlideDirection, setCrumbTrail, useCrumbTrail, type Crumb } from "../lib/crumbTrail";

export type { Crumb };

const HostedContext = createContext(false);

const SLIDE = {
  enter: (direction: 1 | -1) => ({ x: direction > 0 ? 28 : -28, opacity: 0 }),
  center: { x: 0, opacity: 1 },
  exit: (direction: 1 | -1) => ({ x: direction > 0 ? -28 : 28, opacity: 0 }),
};

const SLIDE_TRANSITION = { duration: 0.2, ease: "easeOut" as const };

function CrumbLabel({ part, isLast }: { part: Crumb; isLast: boolean }) {
  if (part.to && !isLast) {
    return <Link to={part.to}>{part.label}</Link>;
  }
  if (part.onClick && !isLast) {
    return (
      <button type="button" onClick={part.onClick}>
        {part.label}
      </button>
    );
  }
  return <span aria-current={isLast ? "page" : undefined}>{part.label}</span>;
}

function CrumbsList({ parts }: { parts: Crumb[] }) {
  return (
    <>
      {parts.map((part, index) => {
        const isLast = index === parts.length - 1;
        return (
          <span key={part.label} className="crumbs__item">
            <CrumbLabel part={part} isLast={isLast} />
            {!isLast && <span className="crumbs__sep">/</span>}
          </span>
        );
      })}
    </>
  );
}

function AnimatedCrumbsList({ parts }: { parts: Crumb[] }) {
  const prevCount = useRef(parts.length);
  const booted = useRef(false);
  const skipEnter = !booted.current;
  if (parts.length > 0) booted.current = true;

  const direction = crumbSlideDirection(prevCount.current, parts.length);
  prevCount.current = parts.length;

  return (
    <AnimatePresence mode="popLayout" initial={false} custom={direction}>
      {parts.map((part, index) => {
        const isLast = index === parts.length - 1;
        return (
          <motion.span
            key={part.label}
            className="crumbs__item"
            layout="position"
            custom={direction}
            variants={SLIDE}
            initial={skipEnter ? false : "enter"}
            animate="center"
            exit="exit"
            transition={SLIDE_TRANSITION}
          >
            <CrumbLabel part={part} isLast={isLast} />
            {!isLast && <span className="crumbs__sep">/</span>}
          </motion.span>
        );
      })}
    </AnimatePresence>
  );
}

export function CrumbsNav({
  parts,
  animated = false,
}: {
  parts: Crumb[];
  animated?: boolean;
}) {
  const reduceMotion = useReducedMotion();
  const slide = animated && !reduceMotion;

  return (
    <nav className="crumbs" aria-label="Breadcrumb">
      {slide ? <AnimatedCrumbsList parts={parts} /> : <CrumbsList parts={parts} />}
    </nav>
  );
}

export function CrumbHost({ children }: { children: ReactNode }) {
  useLayoutEffect(() => {
    return () => setCrumbTrail(null);
  }, []);

  return <HostedContext.Provider value={true}>{children}</HostedContext.Provider>;
}

export function HostedCrumbs() {
  const parts = useCrumbTrail();
  if (!parts?.length) return null;
  return (
    <div className="crumbs-host">
      <CrumbsNav parts={parts} animated />
    </div>
  );
}

export function Crumbs({ parts, local = false }: { parts: Crumb[]; local?: boolean }) {
  const hosted = useContext(HostedContext);

  useLayoutEffect(() => {
    if (!hosted || local) return;
    setCrumbTrail(parts);
  }, [hosted, local, parts]);

  if (hosted && !local) return null;
  return <CrumbsNav parts={parts} />;
}

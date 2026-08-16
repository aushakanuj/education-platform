import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { createContext, useContext, useLayoutEffect, useRef, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { setCrumbTrail, useCrumbTrail, type Crumb } from "../lib/crumbTrail";

export type { Crumb };

const HostedContext = createContext(false);

const SLIDE = {
  enter: { x: 28, opacity: 0 },
  center: { x: 0, opacity: 1 },
  exit: { x: 28, opacity: 0 },
};

const SLIDE_TRANSITION = { duration: 0.2, ease: "easeOut" as const };

function CrumbLabel({ part, isLast }: { part: Crumb; isLast: boolean }) {
  if (part.to && !isLast) {
    return (
      <Link to={part.to} title={part.label}>
        {part.label}
      </Link>
    );
  }
  if (part.onClick && !isLast) {
    return (
      <button type="button" onClick={part.onClick} title={part.label}>
        {part.label}
      </button>
    );
  }
  return (
    <span aria-current={isLast ? "page" : undefined} title={part.label}>
      {part.label}
    </span>
  );
}

function CrumbItems({ parts }: { parts: Crumb[] }) {
  return (
    <>
      {parts.map((part, index) => {
        const isLast = index === parts.length - 1;
        return (
          <span key={part.label} className="crumbs__item">
            {index > 0 && <span className="crumbs__sep">/</span>}
            <CrumbLabel part={part} isLast={isLast} />
          </span>
        );
      })}
    </>
  );
}

function AnimatedCrumbsList({ parts }: { parts: Crumb[] }) {
  const booted = useRef(false);
  const skipEnter = !booted.current;
  if (parts.length > 0) booted.current = true;

  return (
    <AnimatePresence mode="popLayout" initial={false}>
      {parts.map((part, index) => {
        const isLast = index === parts.length - 1;
        return (
          <motion.span
            key={part.label}
            className="crumbs__item"
            variants={SLIDE}
            initial={skipEnter ? false : "enter"}
            animate="center"
            exit="exit"
            transition={SLIDE_TRANSITION}
          >
            {index > 0 && <span className="crumbs__sep">/</span>}
            <CrumbLabel part={part} isLast={isLast} />
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
      {slide ? <AnimatedCrumbsList parts={parts} /> : <CrumbItems parts={parts} />}
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

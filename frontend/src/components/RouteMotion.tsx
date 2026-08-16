import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";
import { useLocation } from "react-router-dom";

import { CrumbHost, HostedCrumbs } from "./Crumbs";

const FADE = {
  enter: { opacity: 0 },
  center: { opacity: 1 },
  exit: { opacity: 0 },
};

const FADE_TRANSITION = { duration: 0.2, ease: "easeOut" as const };

/** Page body fades independently of the hosted breadcrumb trail. */
export function RouteMotion({ children }: { children: ReactNode }) {
  const location = useLocation();
  const reduceMotion = useReducedMotion();

  const page = reduceMotion ? (
    <div className="route-motion__page">{children}</div>
  ) : (
    <AnimatePresence mode="wait">
      <motion.div
        key={location.pathname}
        className="route-motion__page"
        variants={FADE}
        initial="enter"
        animate="center"
        exit="exit"
        transition={FADE_TRANSITION}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );

  return (
    <CrumbHost>
      <div className="route-motion">
        <div className="main__inner">
          <HostedCrumbs />
          {page}
        </div>
      </div>
    </CrumbHost>
  );
}

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";
import { useLocation } from "react-router-dom";

const FADE = {
  enter: { opacity: 0 },
  center: { opacity: 1 },
  exit: { opacity: 0 },
};

/** Light fade for shell main content, keyed by pathname. */
export function RouteMotion({ children }: { children: ReactNode }) {
  const location = useLocation();
  const reduceMotion = useReducedMotion();

  if (reduceMotion) {
    return <div className="main__inner">{children}</div>;
  }

  return (
    <div className="route-motion">
      <AnimatePresence mode="wait">
        <motion.div
          key={location.pathname}
          className="main__inner route-motion__page"
          variants={FADE}
          initial="enter"
          animate="center"
          exit="exit"
          transition={{ duration: 0.18, ease: "easeOut" }}
        >
          {children}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

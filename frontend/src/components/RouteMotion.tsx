import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useMemo, useRef, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";

import { ChromePlayedContext, RouteChromeSlotContext, type ChromePlayed } from "./PageChrome";

const FADE = {
  enter: { opacity: 0 },
  center: { opacity: 1 },
  exit: { opacity: 0 },
};

/** Light fade for shell main content, keyed by pathname. Chrome stays outside the fade. */
export function RouteMotion({ children }: { children: ReactNode }) {
  const location = useLocation();
  const reduceMotion = useReducedMotion();
  const [chromeSlot, setChromeSlot] = useState<HTMLElement | null>(null);
  const playedRef = useRef<ChromePlayed>({ crumb: "", parts: [] });
  const snapshots = useRef(new Map<string, ReactNode>());
  const chromeValue = useMemo(() => ({ slot: chromeSlot, enabled: true }), [chromeSlot]);

  snapshots.current.set(location.pathname, children);
  const page = snapshots.current.get(location.pathname);

  const chrome = <div className="route-motion__chrome" ref={setChromeSlot} />;

  if (reduceMotion) {
    return (
      <ChromePlayedContext.Provider value={playedRef}>
        <RouteChromeSlotContext.Provider value={chromeValue}>
          <div className="main__inner">
            {chrome}
            {page}
          </div>
        </RouteChromeSlotContext.Provider>
      </ChromePlayedContext.Provider>
    );
  }

  return (
    <ChromePlayedContext.Provider value={playedRef}>
      <RouteChromeSlotContext.Provider value={chromeValue}>
        <div className="route-motion">
          {chrome}
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              className="main__inner route-motion__page"
              variants={FADE}
              initial="enter"
              animate="center"
              exit="exit"
              transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
            >
              {page}
            </motion.div>
          </AnimatePresence>
        </div>
      </RouteChromeSlotContext.Provider>
    </ChromePlayedContext.Provider>
  );
}

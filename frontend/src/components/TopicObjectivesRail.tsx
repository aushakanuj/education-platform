import { useState } from "react";

const OBJECTIVES_COLLAPSED_KEY = "ep.objectivesCollapsed";

function readCollapsed(): boolean {
  try {
    const stored = window.localStorage.getItem(OBJECTIVES_COLLAPSED_KEY);
    if (stored !== null) return stored === "1";
  } catch {
    /* ignore */
  }
  if (typeof window.matchMedia !== "function") return false;
  return window.matchMedia("(max-width: 1100px)").matches;
}

export function TopicObjectivesRail({
  objectives,
  onCollapsedChange,
}: {
  objectives: string[];
  onCollapsedChange?: (collapsed: boolean) => void;
}) {
  const [collapsed, setCollapsed] = useState(() =>
    typeof window !== "undefined" ? readCollapsed() : true,
  );

  function toggleCollapsed() {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(OBJECTIVES_COLLAPSED_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      onCollapsedChange?.(next);
      return next;
    });
  }

  if (objectives.length === 0) return null;

  return (
    <aside
      className={`objectives-rail ${collapsed ? "is-collapsed" : ""}`}
      aria-label="Objectives"
    >
      <div className="objectives-rail__top">
        <button
          type="button"
          className="objectives-rail__toggle"
          aria-expanded={!collapsed}
          aria-controls="topic-objectives-list"
          title={collapsed ? "Expand objectives" : "Collapse objectives"}
          aria-label={collapsed ? "Expand objectives" : "Collapse objectives"}
          onClick={toggleCollapsed}
        >
          {collapsed ? "«" : "»"}
        </button>
        {!collapsed && <h2 className="objectives-rail__title">Objectives</h2>}
      </div>
      <div className="objectives-rail__body">
        <span className="objectives-rail__short" aria-hidden="true">
          O
        </span>
        <div id="topic-objectives-list" className="objectives-rail__content" hidden={collapsed}>
          <ul className="objectives">
            {objectives.map((objective) => (
              <li key={objective}>{objective}</li>
            ))}
          </ul>
        </div>
      </div>
    </aside>
  );
}

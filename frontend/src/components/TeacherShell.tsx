import { Link, Outlet, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";

import { useAuth } from "../auth/AuthContext";
import { PushButton } from "./PushButton";

const RAIL_COLLAPSED_KEY = "ep.teacherRailCollapsed";

function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(RAIL_COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

export function TeacherShell() {
  const { user, signOut, isDevMockSession } = useAuth();
  const location = useLocation();
  const [railCollapsed, setRailCollapsed] = useState(false);

  useEffect(() => {
    setRailCollapsed(readCollapsed());
  }, []);

  function toggleRail() {
    setRailCollapsed((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(RAIL_COLLAPSED_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  }

  const onClasses =
    location.pathname === "/teacher" || location.pathname.startsWith("/teacher/classes");
  const onAssistant = location.pathname.startsWith("/teacher/assistant");

  return (
    <div className="app-frame">
      <div className="demo-banner" role="status">
        Demo mockup only · Calm Humanist · Teacher workspace · fixture data
      </div>
      <div className={`app ${railCollapsed ? "is-rail-collapsed" : ""}`}>
        <aside
          className={`rail ${railCollapsed ? "is-collapsed" : ""}`}
          aria-label="Primary"
        >
          <div className="rail__top">
            {!railCollapsed && (
              <Link to="/teacher" className="rail__brand">
                Education Platform
              </Link>
            )}
            <button
              type="button"
              className="rail__toggle"
              aria-expanded={!railCollapsed}
              aria-controls="teacher-rail-nav"
              title={railCollapsed ? "Expand navigation" : "Collapse navigation"}
              aria-label={railCollapsed ? "Expand navigation" : "Collapse navigation"}
              onClick={toggleRail}
            >
              {railCollapsed ? "»" : "«"}
            </button>
          </div>
          <nav id="teacher-rail-nav" className="rail__nav" aria-label="Teacher">
            <Link
              to="/teacher"
              className={`rail__link ${onClasses ? "is-active" : ""}`}
              title="My classes"
            >
              <span className="rail__link-short" aria-hidden="true">
                C
              </span>
              <span className="rail__link-label">My classes</span>
            </Link>
            <Link
              to="/teacher/assistant"
              className={`rail__link ${onAssistant ? "is-active" : ""}`}
              title="Assistant"
            >
              <span className="rail__link-short" aria-hidden="true">
                A
              </span>
              <span className="rail__link-label">Assistant</span>
            </Link>
          </nav>
          <div className="rail__user">
            <div className="rail__name">{user?.full_name ?? "Teacher"}</div>
            <div className="rail__meta">
              {[isDevMockSession ? "DEV mock" : null, "Teacher", "Demo School"]
                .filter(Boolean)
                .join(" · ")}
            </div>
            <PushButton variant="soft" size="sm" onClick={() => void signOut()}>
              Sign out
            </PushButton>
          </div>
        </aside>

        <div className="app__content">
          <div className="topbar">
            <div className="topbar__row">
              <Link to="/teacher" className="topbar__brand">
                Education Platform
              </Link>
              <PushButton variant="outline" size="sm" onClick={() => void signOut()}>
                Sign out
              </PushButton>
            </div>
            <nav className="rail__nav rail__nav--horizontal" aria-label="Mobile teacher">
              <Link to="/teacher" className={`rail__link ${onClasses ? "is-active" : ""}`}>
                My classes
              </Link>
              <Link
                to="/teacher/assistant"
                className={`rail__link ${onAssistant ? "is-active" : ""}`}
              >
                Assistant
              </Link>
            </nav>
          </div>

          <main className="main">
            <div className="main__inner">
              <Outlet />
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}

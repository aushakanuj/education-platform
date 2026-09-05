import { Link, Outlet, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";

import { useAuth } from "../auth/AuthContext";
import { PushButton } from "./PushButton";
import { RouteMotion } from "./RouteMotion";

const RAIL_COLLAPSED_KEY = "ep.adminRailCollapsed";

function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(RAIL_COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

export function AdminShell() {
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

  const onMaterials = location.pathname.startsWith("/admin/materials");
  const onDocuments = location.pathname.startsWith("/admin/documents");
  const onPolicy = location.pathname.startsWith("/admin/policy");
  const onAtRisk = location.pathname.startsWith("/admin/at-risk");

  return (
    <div className="app-frame">
      <div className="demo-banner" role="status">
        {isDevMockSession
          ? "Demo mockup only · Admin fixture session · materials need a real JWT"
          : "Demo mockup only · Admin · live published materials API"}
      </div>
      <div className={`app ${railCollapsed ? "is-rail-collapsed" : ""}`}>
        <aside
          className={`rail ${railCollapsed ? "is-collapsed" : ""}`}
          aria-label="Admin primary"
          data-elevated="true"
        >
          <div className="rail__top">
            {!railCollapsed && (
              <Link to="/admin/materials" className="rail__brand">
                Education Platform
              </Link>
            )}
            <button
              type="button"
              className="rail__toggle"
              aria-expanded={!railCollapsed}
              aria-controls="admin-rail-nav"
              title={railCollapsed ? "Expand navigation" : "Collapse navigation"}
              aria-label={railCollapsed ? "Expand navigation" : "Collapse navigation"}
              onClick={toggleRail}
            >
              {railCollapsed ? "»" : "«"}
            </button>
          </div>
          <nav id="admin-rail-nav" className="rail__nav" aria-label="Admin">
            <Link
              to="/admin/materials"
              className={`rail__link ${onMaterials ? "is-active" : ""}`}
              title="Materials"
            >
              <span className="rail__link-short" aria-hidden="true">
                M
              </span>
              <span className="rail__link-label">Materials</span>
            </Link>
            <Link
              to="/admin/documents"
              className={`rail__link ${onDocuments ? "is-active" : ""}`}
              title="Documents"
            >
              <span className="rail__link-short" aria-hidden="true">
                D
              </span>
              <span className="rail__link-label">Documents</span>
            </Link>
            <Link
              to="/admin/policy"
              className={`rail__link ${onPolicy ? "is-active" : ""}`}
              title="Policy assistant"
            >
              <span className="rail__link-short" aria-hidden="true">
                P
              </span>
              <span className="rail__link-label">Policy assistant</span>
            </Link>
            <Link
              to="/admin/at-risk"
              className={`rail__link ${onAtRisk ? "is-active" : ""}`}
              title="At-risk flags"
            >
              <span className="rail__link-short" aria-hidden="true">
                !
              </span>
              <span className="rail__link-label">At-risk flags</span>
            </Link>
          </nav>
          <div className="rail__user">
            <div className="rail__name">{user?.full_name ?? "Administrator"}</div>
            <div className="rail__meta">Administrator · Demo School</div>
            <PushButton variant="soft" size="sm" onClick={() => void signOut()}>
              Sign out
            </PushButton>
          </div>
        </aside>

        <div className="app__content">
          <div className="topbar">
            <div className="topbar__row">
              <Link to="/admin/materials" className="topbar__brand">
                Education Platform
              </Link>
              <PushButton variant="outline" size="sm" onClick={() => void signOut()}>
                Sign out
              </PushButton>
            </div>
            <nav className="rail__nav rail__nav--horizontal" aria-label="Mobile admin">
              <Link
                to="/admin/materials"
                className={`rail__link ${onMaterials ? "is-active" : ""}`}
              >
                Materials
              </Link>
              <Link
                to="/admin/documents"
                className={`rail__link ${onDocuments ? "is-active" : ""}`}
              >
                Documents
              </Link>
              <Link to="/admin/policy" className={`rail__link ${onPolicy ? "is-active" : ""}`}>
                Policy assistant
              </Link>
              <Link to="/admin/at-risk" className={`rail__link ${onAtRisk ? "is-active" : ""}`}>
                At-risk flags
              </Link>
            </nav>
          </div>

          <main className="main">
            <RouteMotion>
              <Outlet />
            </RouteMotion>
          </main>
        </div>
      </div>
    </div>
  );
}

import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useEffect, useState } from "react";

import { resetDemoProgress } from "../api/demo";
import { ApiError } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { ConfirmDialog } from "./ConfirmDialog";
import { PushButton } from "./PushButton";

const IS_DEV = import.meta.env.DEV;
const RAIL_COLLAPSED_KEY = "ep.railCollapsed";

function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(RAIL_COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

export function AppShell({
  children,
  subjectTitle,
}: {
  children: React.ReactNode;
  subjectTitle?: string;
}) {
  const { user, enrollments, enrolled, signOut } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const { subjectId } = useParams();
  const [resetOpen, setResetOpen] = useState(false);
  const [resetBusy, setResetBusy] = useState(false);
  const [resetError, setResetError] = useState<string | null>(null);
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

  const grade = enrollments?.grade_enrollments.find((g) => g.status === "active");

  const onSubjects = location.pathname === "/" || location.pathname === `/subjects/${subjectId}`;
  const onSubjectMaterial =
    Boolean(subjectId) &&
    (location.pathname.startsWith(`/subjects/${subjectId}/`) ||
      location.pathname.startsWith("/quizzes/") ||
      location.pathname.startsWith("/attempts/"));

  const subjectPath = enrolled && subjectId ? `/subjects/${subjectId}` : enrolled ? "/" : "/enroll";

  const homeTo = enrolled ? "/" : "/enroll";
  const metaParts = [grade?.grade_name ?? "Grade 8", "Demo School"];
  const subjectLabel = subjectTitle ?? "School material";

  async function onResetDemo() {
    setResetBusy(true);
    setResetError(null);
    try {
      await resetDemoProgress();
      setResetOpen(false);
      navigate("/", { replace: true });
      window.location.assign("/");
    } catch (err) {
      setResetError(err instanceof ApiError ? err.message : "Could not reset demo.");
      setResetBusy(false);
    }
  }

  return (
    <div className="app-frame">
      <div className="demo-banner" role="status">
        Demo mockup only · Calm Humanist · Source Sans 3 + IBM Plex Mono · live API
      </div>
      <div className={`app ${railCollapsed ? "is-rail-collapsed" : ""}`}>
        <aside
          className={`rail ${railCollapsed ? "is-collapsed" : ""}`}
          aria-label="Primary"
        >
          <div className="rail__top">
            {!railCollapsed && (
              <Link to={homeTo} className="rail__brand">
                Education Platform
              </Link>
            )}
            <button
              type="button"
              className="rail__toggle"
              aria-expanded={!railCollapsed}
              aria-controls="primary-rail-nav"
              title={railCollapsed ? "Expand navigation" : "Collapse navigation"}
              aria-label={railCollapsed ? "Expand navigation" : "Collapse navigation"}
              onClick={toggleRail}
            >
              {railCollapsed ? "»" : "«"}
            </button>
          </div>
          <nav id="primary-rail-nav" className="rail__nav" aria-label="Study">
            <Link
              to={homeTo}
              className={`rail__link ${onSubjects ? "is-active" : ""}`}
              title="Subjects"
            >
              <span className="rail__link-short" aria-hidden="true">
                S
              </span>
              <span className="rail__link-label">Subjects</span>
            </Link>
            {subjectId ? (
              <Link
                to={subjectPath}
                className={`rail__link ${onSubjectMaterial ? "is-active" : ""}`}
                title={subjectLabel}
              >
                <span className="rail__link-short" aria-hidden="true">
                  M
                </span>
                <span className="rail__link-label">{subjectLabel}</span>
              </Link>
            ) : (
              <span
                className="rail__link is-disabled"
                aria-disabled="true"
                title="School material"
              >
                <span className="rail__link-short" aria-hidden="true">
                  M
                </span>
                <span className="rail__link-label">School material</span>
              </span>
            )}
          </nav>
          <div className="rail__user">
            <div className="rail__name">{user?.full_name ?? "Asha Student"}</div>
            <div className="rail__meta">{metaParts.join(" · ")}</div>
            {IS_DEV && enrolled && (
              <PushButton
                variant="outline"
                size="sm"
                onClick={() => {
                  setResetError(null);
                  setResetOpen(true);
                }}
              >
                Reset demo
              </PushButton>
            )}
            <PushButton variant="soft" size="sm" onClick={() => void signOut()}>
              Sign out
            </PushButton>
          </div>
        </aside>

        <div className="app__content">
          <div className="topbar">
            <div className="topbar__row">
              <Link to={homeTo} className="topbar__brand">
                Education Platform
              </Link>
              <PushButton variant="outline" size="sm" onClick={() => void signOut()}>
                Sign out
              </PushButton>
            </div>
            <nav className="rail__nav rail__nav--horizontal" aria-label="Mobile study">
              <Link to={homeTo} className={`rail__link ${onSubjects ? "is-active" : ""}`}>
                Subjects
              </Link>
              {subjectId ? (
                <Link to={subjectPath} className={`rail__link ${onSubjectMaterial ? "is-active" : ""}`}>
                  {subjectLabel}
                </Link>
              ) : (
                <span className="rail__link is-disabled" aria-disabled="true">
                  School material
                </span>
              )}
            </nav>
          </div>

          <main className="main">
            <div className="main__inner">{children}</div>
          </main>
        </div>
      </div>

      <ConfirmDialog
        open={resetOpen}
        title="Demo reset"
        body={
          resetError ??
          "All quiz progress and attempt history will be cleared. Subjects start fresh."
        }
        onDismiss={() => {
          if (!resetBusy) setResetOpen(false);
        }}
        actions={[
          { label: "Cancel", variant: "soft" },
          {
            label: resetBusy ? "Resetting…" : "Reset demo",
            keepOpen: true,
            onClick: () => {
              void onResetDemo();
            },
          },
        ]}
      />
    </div>
  );
}

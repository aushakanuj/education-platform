import { useState, type MouseEvent } from "react";
import { Navigate } from "react-router-dom";

import { enrollPocMath } from "../api/enrollments";
import { ApiError } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { AppShell } from "../components/AppShell";
import { PushButton } from "../components/PushButton";
import { StudyBuddy } from "../components/StudyBuddy";

export function EnrollPage() {
  const { enrolled, setEnrollments } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [burst, setBurst] = useState<{ x: number; y: number } | null>(null);

  if (enrolled) {
    return <Navigate to="/" replace />;
  }

  async function onEnroll(e: MouseEvent<HTMLButtonElement>) {
    setError(null);
    setBusy(true);
    const rect = e.currentTarget.getBoundingClientRect();
    setBurst({
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    });
    try {
      const summary = await enrollPocMath(true);
      setEnrollments(summary);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not enroll. Try again.");
      setBurst(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell>
      <header className="page-head">
        <div>
          <h1 className="page-head__title">1.0 Enroll</h1>
          <p className="page-head__lede">
            Join Grade 8 Mathematics for this POC. Until you enroll, lessons and quizzes stay locked.
          </p>
        </div>
        <StudyBuddy size="lg" />
      </header>

      <div className="banner--info stack-gap">
        <p>
          You will be enrolled in <strong>Grade 8 · Mathematics</strong> for academic period{" "}
          <strong>2026-27</strong> at POC Demo School.
        </p>
        {error && (
          <p className="form__error" role="alert">
            {error}
          </p>
        )}
        <div style={{ position: "relative", display: "inline-block" }}>
          <PushButton
            color="pear"
            size="lg"
            loading={busy}
            onClick={(e) => void onEnroll(e)}
          >
            Enroll me <span className="btn__arrow">→</span>
          </PushButton>
          {burst && (
            <span
              className="star-burst"
              style={{ left: burst.x, top: burst.y }}
              onAnimationEnd={() => setBurst(null)}
            />
          )}
        </div>
      </div>
    </AppShell>
  );
}

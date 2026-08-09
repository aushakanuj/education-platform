import { useState } from "react";
import { Navigate } from "react-router-dom";

import { enrollPocMath } from "../api/enrollments";
import { ApiError } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { AppShell } from "../components/AppShell";
import { PushButton } from "../components/PushButton";

const IS_DEV = import.meta.env.DEV;

export function EnrollPage() {
  const { enrolled, setEnrollments } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (enrolled) {
    return <Navigate to="/" replace />;
  }

  async function onEnroll() {
    setError(null);
    setBusy(true);
    try {
      const summary = await enrollPocMath(true);
      setEnrollments(summary);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not enroll. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell>
      <header className="page-head">
        <p className="kicker">Enroll</p>
        <h1>Join Grade 8 Mathematics</h1>
        <p>Until you enroll, lessons and quizzes stay locked.</p>
      </header>

      <div className="panel stack-gap">
        {IS_DEV ? (
          <>
            <p>
              Development helper: enroll in <strong>Grade 8 · Mathematics</strong> for academic
              period <strong>2026-27</strong> at POC Demo School.
            </p>
            {error && (
              <p className="form__error" role="alert">
                {error}
              </p>
            )}
            <div>
              <PushButton size="lg" loading={busy} onClick={() => void onEnroll()}>
                Enroll me
              </PushButton>
            </div>
          </>
        ) : (
          <div className="banner--info">
            <p>
              Your administrator provisions enrollments. Ask them to enroll you in Grade 8
              Mathematics, then sign in again.
            </p>
          </div>
        )}
      </div>
    </AppShell>
  );
}

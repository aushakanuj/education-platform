import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";

import { ApiError } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { PushButton } from "../components/PushButton";
import { StudyBuddy } from "../components/StudyBuddy";

type Mode = "login" | "create";

export function WelcomePage() {
  const { user, enrolled, loading, signIn, createStudent } = useAuth();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [studentId, setStudentId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!loading && user) {
    return <Navigate to={enrolled ? "/" : "/enroll"} replace />;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") {
        await signIn(email.trim(), password);
      } else {
        await createStudent({
          email: email.trim(),
          password,
          full_name: fullName.trim(),
          student_identifier: studentId.trim() || `S-${Date.now()}`,
        });
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="welcome">
      <div className="welcome__inner">
        <div className="welcome__brand">
          <StudyBuddy size="lg" />
          Education Platform
        </div>
        <p className="welcome__lede">Sign in, enroll, read a lesson, then take the quiz.</p>

        <div className="tabs" role="tablist" aria-label="Account">
          <button
            type="button"
            role="tab"
            className={`tabs__btn ${mode === "login" ? "is-active" : ""}`}
            aria-selected={mode === "login"}
            onClick={() => setMode("login")}
          >
            Sign in
          </button>
          <button
            type="button"
            role="tab"
            className={`tabs__btn ${mode === "create" ? "is-active" : ""}`}
            aria-selected={mode === "create"}
            onClick={() => setMode("create")}
          >
            Create student
          </button>
        </div>

        <form className="form" onSubmit={(e) => void onSubmit(e)}>
          {mode === "create" && (
            <>
              <div className="form__field">
                <label className="form__label" htmlFor="full_name">
                  Your name
                </label>
                <input
                  id="full_name"
                  className="form__input"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  required
                  autoComplete="name"
                />
              </div>
              <div className="form__field">
                <label className="form__label" htmlFor="student_id">
                  Student ID
                </label>
                <input
                  id="student_id"
                  className="form__input"
                  value={studentId}
                  onChange={(e) => setStudentId(e.target.value)}
                  placeholder="S1"
                  autoComplete="off"
                />
              </div>
            </>
          )}
          <div className="form__field">
            <label className="form__label" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              type="email"
              className="form__input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
            />
          </div>
          <div className="form__field">
            <label className="form__label" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              className="form__input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={mode === "create" ? 8 : 1}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
            />
          </div>
          {error && (
            <p className="form__error" role="alert">
              {error}
            </p>
          )}
          <div className="form__actions">
            <PushButton type="submit" loading={busy} color="pear">
              {mode === "login" ? (
                <>
                  Sign in <span className="btn__arrow">→</span>
                </>
              ) : (
                <>
                  Create and sign in <span className="btn__arrow">→</span>
                </>
              )}
            </PushButton>
          </div>
        </form>
      </div>
      <footer className="welcome__footer">
        <strong>Soft, but exact.</strong> Study one topic at a time.
      </footer>
    </div>
  );
}

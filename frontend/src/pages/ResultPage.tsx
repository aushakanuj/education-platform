import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";

import { getAttempt } from "../api/attempts";
import type { AttemptResult } from "../api/types";
import { ApiError } from "../api/types";
import { AppShell } from "../components/AppShell";
import { PushButton } from "../components/PushButton";
import { StudyBuddy } from "../components/StudyBuddy";

export function ResultPage() {
  const { attemptId = "" } = useParams();
  const location = useLocation();
  const fromState = (location.state as { result?: AttemptResult } | null)?.result;
  const [result, setResult] = useState<AttemptResult | null>(fromState ?? null);
  const [error, setError] = useState<string | null>(null);
  const [burst, setBurst] = useState(false);

  useEffect(() => {
    if (fromState) {
      if (fromState.passed) {
        setBurst(true);
      }
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const data = await getAttempt(attemptId);
        if (!cancelled) {
          setResult(data);
          if (data.passed) {
            setBurst(true);
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Could not load result.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [attemptId, fromState]);

  const percent =
    result?.score_percent === null || result?.score_percent === undefined
      ? null
      : Number(result.score_percent);

  return (
    <AppShell>
      {!result && !error && (
        <div className="center-state" role="status">
          Loading result…
        </div>
      )}

      {error && (
        <div className="center-state">
          <p className="form__error" role="alert">
            {error}
          </p>
          <Link to="/">
            <PushButton variant="soft">Back to topics</PushButton>
          </Link>
        </div>
      )}

      {result && (
        <div>
          <header className="page-head">
            <div>
              <p className="muted" style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)" }}>
                4.0 Result · Attempt {result.attempt_number}
              </p>
              <h1 className="page-head__title">Your score</h1>
            </div>
            <StudyBuddy size="lg" />
          </header>

          <div className={`score-hero ${result.passed ? "is-pass" : ""}`}>
            {burst && result.passed && (
              <span
                className="star-burst"
                style={{ left: "2rem", top: "2rem" }}
                onAnimationEnd={() => setBurst(false)}
              />
            )}
            <div className="score-hero__value">
              {percent === null ? "—" : `${Math.round(percent)}%`}
            </div>
            <p className="score-hero__status">
              {result.passed ? "Passed — nice work." : "Not yet — review the lesson and try again."}
            </p>
            <p className="muted">
              Raw score {result.score_raw ?? "—"} · Pass mark 70%
            </p>
          </div>

          <h2 style={{ fontSize: "var(--text-xl)", marginBottom: "var(--space-md)" }}>
            Question review
          </h2>
          <p className="muted" style={{ marginBottom: "var(--space-md)" }}>
            Correct answers stay hidden. You only see which ones you got right.
          </p>

          <div className="answer-review">
            {result.answers.map((a) => (
              <div
                key={a.question_number}
                className={`answer-row ${a.is_correct ? "is-correct" : "is-wrong"}`}
              >
                <span className="answer-row__num">Q{a.question_number}</span>
                <span>
                  You chose <strong>{a.selected_option_label ?? "—"}</strong>
                </span>
                <span className="answer-row__mark">
                  {a.is_correct ? "Correct" : "Incorrect"}
                </span>
              </div>
            ))}
          </div>

          <div className="form__actions" style={{ marginTop: "var(--space-xl)" }}>
            <Link to={`/topics/${result.topic_id}`}>
              <PushButton variant="soft">Review lesson</PushButton>
            </Link>
            <Link to="/">
              <PushButton color="pear">
                Back to topics <span className="btn__arrow">→</span>
              </PushButton>
            </Link>
          </div>
        </div>
      )}
    </AppShell>
  );
}

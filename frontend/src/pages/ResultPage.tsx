import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import { getAttempt } from "../api/attempts";
import { fetchLearningDirectory } from "../api/materials";
import type { AttemptResult } from "../api/types";
import { ApiError } from "../api/types";
import { AppShell } from "../components/AppShell";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Crumbs } from "../components/Crumbs";
import { PushButton } from "../components/PushButton";
import { resolvePathFromAttempt, type LearningPath } from "../lib/learningPath";

export function ResultPage() {
  const { attemptId = "" } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const state = location.state as { result?: AttemptResult; path?: LearningPath } | null;
  const fromState = state?.result;
  const [result, setResult] = useState<AttemptResult | null>(fromState ?? null);
  const [path, setPath] = useState<LearningPath | null>(state?.path ?? null);
  const [error, setError] = useState<string | null>(null);
  const [showUnlockDialog, setShowUnlockDialog] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = fromState ?? (await getAttempt(attemptId));
        const directory = await fetchLearningDirectory();
        if (cancelled) return;
        setResult(data);
        const resolved = resolvePathFromAttempt(directory, data);
        setPath(resolved);
        const unlockedNow =
          data.scope === "subtopic_mastery" &&
          Boolean(data.passed) &&
          Boolean(resolved?.overallUnlocked);
        setShowUnlockDialog(unlockedNow);
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
  const passMark =
    result?.pass_threshold_percent == null
      ? 70
      : Math.round(Number(result.pass_threshold_percent));
  const held = result != null && !result.review_available;
  const topicPath = path?.topicPath ?? "/";
  const rawScore =
    result?.score_raw == null
      ? null
      : typeof result.score_raw === "string"
        ? result.score_raw
        : String(result.score_raw);

  return (
    <AppShell topicTitle={path?.topicTitle}>
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
            <PushButton variant="soft">Back to subjects</PushButton>
          </Link>
        </div>
      )}

      {result && (
        <div>
          {path && (
            <>
              <Crumbs
                parts={[
                  { label: "Subjects", to: "/" },
                  { label: path.subjectName, to: `/subjects/${path.subjectId}` },
                  { label: path.topicTitle, to: path.topicPath },
                  { label: "Result" },
                ]}
              />
              <div className="back-row">
                <Link to={path.topicPath} className="btn btn--outline btn--sm">
                  ← Back to topic
                </Link>
              </div>
            </>
          )}

          <header className="page-head">
            <p className="kicker">
              Result · Attempt {result.attempt_number}
              {result.scope === "topic_mastery" ? " · overall quiz" : ""}
            </p>
            <h1>{held ? "Result pending release" : "Your score"}</h1>
          </header>

          {held ? (
            <div className="alert alert--info" role="status">
              Your answers were submitted. Scores stay hidden until the teacher releases results.
            </div>
          ) : (
            <div className={`score-hero ${result.passed ? "is-pass" : ""}`}>
              <p className="score-hero__value">
                {percent === null ? "—" : `${Math.round(percent)}%`}
              </p>
              <p className="score-hero__status">
                {result.passed
                  ? "Passed — nice work."
                  : "Not yet — review the lesson and try again."}
              </p>
              <p className="score-hero__meta">
                Raw {rawScore ?? "—"} · Pass mark {passMark}%
              </p>
            </div>
          )}

          {!held && path?.overallUnlocked && result.scope === "subtopic_mastery" && result.passed && (
            <div className="alert alert--success">
              All subtopic quizzes passed. The overall topic quiz is now unlocked.
            </div>
          )}
          {!held && path?.topicComplete && (
            <div className="alert alert--success">
              Topic complete — every subtopic and the overall quiz are passed.
            </div>
          )}

          {result.review_available && result.answers.length > 0 && (
            <>
              <h2 className="section-title">Question review</h2>
              <p className="muted" style={{ marginBottom: "0.75rem", fontSize: "0.95rem" }}>
                Correct answer keys stay hidden. You only see which items you got right.
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
            </>
          )}

          <div className="actions">
            {result.scope === "subtopic_mastery" && path?.lessonPath && (
              <Link to={path.lessonPath} className="btn btn--soft">
                Review lesson
              </Link>
            )}
            <Link to={`/quizzes/${result.quiz_id}`} className="btn btn--outline">
              Retake quiz
            </Link>
            <Link to={topicPath} className="btn">
              Back to topic
            </Link>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={showUnlockDialog}
        title="Overall quiz unlocked"
        body="You finished every subtopic quiz. Take the overall topic quiz when you are ready."
        onDismiss={() => setShowUnlockDialog(false)}
        actions={[
          { label: "Stay here", variant: "soft" },
          {
            label: "Go to topic",
            onClick: () => navigate(topicPath),
          },
        ]}
      />
    </AppShell>
  );
}

import { Link } from "react-router-dom";

import type { AttemptHistoryItem } from "../api/types";

export function formatAttempt(attempt: AttemptHistoryItem): string {
  const score =
    attempt.score_percent == null ? null : `${Math.round(Number(attempt.score_percent))}%`;
  if (attempt.status === "in_progress") return "In progress";
  if (attempt.passed === true) return `Passed${score ? ` · ${score}` : ""}`;
  if (attempt.passed === false) return `Not passed${score ? ` · ${score}` : ""}`;
  return attempt.status.replaceAll("_", " ");
}

export function AttemptHistoryList({ attempts }: { attempts: AttemptHistoryItem[] }) {
  if (attempts.length === 0) {
    return <p className="history-empty">No attempts recorded yet.</p>;
  }

  return (
    <ul className="history">
      {attempts.map((attempt) => (
        <li key={attempt.id} className="history-item">
          <span className="history-item__num">#{attempt.attempt_number}</span>
          <div>
            <div>{formatAttempt(attempt)}</div>
            <p className="history-item__meta">
              {attempt.submitted_at
                ? new Date(attempt.submitted_at).toLocaleString()
                : attempt.started_at
                  ? new Date(attempt.started_at).toLocaleString()
                  : "—"}
            </p>
          </div>
          <Link to={`/attempts/${attempt.id}`} className="btn btn--soft btn--sm">
            View
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function AttemptHistoryTrigger({
  title,
  attempts,
  onOpen,
  active,
}: {
  title: string;
  attempts: AttemptHistoryItem[];
  onOpen: () => void;
  active?: boolean;
}) {
  const latest = attempts[0];
  return (
    <button
      type="button"
      className={`history-trigger ${active ? "is-active" : ""}`}
      onClick={onOpen}
      aria-pressed={active}
    >
      <div className="history-toggle__label">
        <div className="history-toggle__title">{title}</div>
        <div className="history-toggle__latest">
          {latest ? (
            <>
              Latest: <strong>{formatAttempt(latest)}</strong>
            </>
          ) : (
            "No attempts yet"
          )}
        </div>
      </div>
      <span className="history-trigger__action">{active ? "Viewing" : "Show history"}</span>
    </button>
  );
}

export function AttemptHistory({
  title,
  attempts,
}: {
  title: string;
  attempts: AttemptHistoryItem[];
}) {
  const latest = attempts[0];
  return (
    <details className="history-toggle">
      <summary className="history-toggle__summary">
        <div className="history-toggle__label">
          <div className="history-toggle__title">{title}</div>
          <div className="history-toggle__latest">
            {latest ? (
              <>
                Latest: <strong>{formatAttempt(latest)}</strong>
              </>
            ) : (
              "No attempts yet"
            )}
          </div>
        </div>
        <span className="history-toggle__chevron" aria-hidden="true">
          ▾
        </span>
      </summary>
      <div className="history-toggle__body">
        <AttemptHistoryList attempts={attempts} />
      </div>
    </details>
  );
}

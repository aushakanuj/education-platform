import { Link } from "react-router-dom";

import type { AttemptHistoryItem } from "../api/types";

export function formatAttempt(attempt: AttemptHistoryItem): string {
  const score =
    attempt.score_percent == null ? null : `${Math.round(Number(attempt.score_percent))}%`;
  if (attempt.status === "in_progress") return "Not finished";
  if (attempt.status === "abandoned") return "Abandoned";
  if (attempt.passed === true) return `Passed${score ? ` · ${score}` : ""}`;
  if (attempt.passed === false) return `Not passed${score ? ` · ${score}` : ""}`;
  return attempt.status.replaceAll("_", " ");
}

export function formatAttemptWhen(attempt: AttemptHistoryItem): string | null {
  const when = attempt.submitted_at ?? attempt.started_at;
  if (!when) return null;
  return new Date(when).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
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
  to,
  actionLabel,
}: {
  title: string;
  attempts: AttemptHistoryItem[];
  onOpen?: () => void;
  active?: boolean;
  to?: string;
  actionLabel?: string;
}) {
  const latest = attempts[0];
  const action = actionLabel ?? (active ? "Viewing" : to ? "Open quiz" : "Show history");
  const body = (
    <>
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
      <span className="history-trigger__action">{action}</span>
    </>
  );

  if (to) {
    return (
      <Link to={to} className="history-trigger">
        {body}
      </Link>
    );
  }

  return (
    <button
      type="button"
      className={`history-trigger ${active ? "is-active" : ""}`}
      onClick={onOpen}
      aria-pressed={active}
    >
      {body}
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

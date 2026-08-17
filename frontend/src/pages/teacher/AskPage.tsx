import { useState } from "react";

import { Crumbs } from "../../components/Crumbs";
import { PushButton } from "../../components/PushButton";
import { askStudents, type AskAnswer } from "../../api/insights";

const SUGGESTIONS = [
  "which of my students are below 60%?",
  "average mastery by section",
  "who has attendance below 75 percent?",
];

export function AskPage() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AskAnswer | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSql, setShowSql] = useState(false);

  async function ask(text: string) {
    const asked = text.trim();
    if (!asked || pending) return;
    setPending(true);
    setError(null);
    try {
      setAnswer(await askStudents(asked));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not reach the assistant.");
      setAnswer(null);
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      <Crumbs parts={[{ label: "My classes", to: "/teacher" }, { label: "Assistant" }]} />
      <header className="page-head">
        <p className="kicker">Teacher · ask the data</p>
        <h1>Assistant</h1>
        <p>
          Ask about your students in plain English. Answers cover only the classes you teach —
          asking about anything else returns nothing rather than an error.
        </p>
      </header>

      <form
        className="card"
        onSubmit={(event) => {
          event.preventDefault();
          void ask(question);
        }}
      >
        <label className="field">
          <span className="field__label">Your question</span>
          <input
            className="field__input"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="how many of my students are below 40% in maths?"
            maxLength={500}
            aria-label="Your question"
          />
        </label>
        <div className="meta-row">
          <PushButton type="submit" disabled={pending || question.trim().length === 0}>
            {pending ? "Asking…" : "Ask"}
          </PushButton>
        </div>
        <div className="meta-row">
          {SUGGESTIONS.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              className="badge badge--info"
              onClick={() => {
                setQuestion(suggestion);
                void ask(suggestion);
              }}
            >
              {suggestion}
            </button>
          ))}
        </div>
      </form>

      {error && (
        <div className="banner banner--warning" role="alert">
          {error}
        </div>
      )}

      {answer && !answer.answered && (
        <div className="banner banner--info" role="status">
          {answer.reason ?? "That question could not be answered from this data."}
        </div>
      )}

      {answer?.answered && (
        <section className="card" aria-label="Answer">
          <div className="topics-section__head">
            <h2>
              {answer.row_count} result{answer.row_count === 1 ? "" : "s"}
            </h2>
            <p>
              {answer.truncated ? "Showing the first page of results. " : ""}
              Narrowed to your classes.
            </p>
          </div>

          {answer.row_count === 0 ? (
            <p className="progress-label">
              Nothing matched inside your classes. That is not an error — you may be asking
              about students another teacher is responsible for.
            </p>
          ) : (
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    {answer.columns.map((column) => (
                      <th key={column}>{column.replace(/_/g, " ")}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {answer.rows.map((row, rowIndex) => (
                    <tr key={rowIndex}>
                      {row.map((cell, cellIndex) => (
                        <td key={cellIndex}>{cell === null ? "—" : String(cell)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="meta-row">
            <button
              type="button"
              className="badge"
              aria-expanded={showSql}
              onClick={() => setShowSql((prev) => !prev)}
            >
              {showSql ? "Hide" : "Show"} the query behind this
            </button>
          </div>

          {showSql && (
            <>
              <p className="progress-label">What the assistant wrote</p>
              <pre className="code-block">{answer.model_sql}</pre>
              <p className="progress-label">
                What actually ran — the platform adds your permission boundary afterwards
              </p>
              <pre className="code-block">{answer.executed_sql}</pre>
            </>
          )}
        </section>
      )}
    </>
  );
}

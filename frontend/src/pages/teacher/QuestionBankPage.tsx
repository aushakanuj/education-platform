import { useEffect, useMemo, useState } from "react";

import { Crumbs } from "../../components/Crumbs";
import { PushButton } from "../../components/PushButton";
import {
  discardDraft,
  fetchAuthorableSubtopics,
  fetchDrafts,
  generateQuestions,
  publishDraft,
  type AuthorableSubtopic,
  type Difficulty,
  type DraftQuestion,
} from "../../api/authoring";

const DIFFICULTIES: Difficulty[] = ["easy", "medium", "hard"];

export function QuestionBankPage() {
  const [subtopics, setSubtopics] = useState<AuthorableSubtopic[]>([]);
  const [selected, setSelected] = useState("");
  const [count, setCount] = useState(5);
  const [difficulty, setDifficulty] = useState<Difficulty>("medium");

  const [drafts, setDrafts] = useState<DraftQuestion[]>([]);
  const [rejected, setRejected] = useState<string[]>([]);
  const [generating, setGenerating] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetchAuthorableSubtopics()
      .then((list) => {
        if (cancelled) return;
        setSubtopics(list);
        setSelected((current) => current || list[0]?.id || "");
      })
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Could not load your subjects."),
      )
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    setRejected([]);
    fetchDrafts(selected)
      .then((list) => !cancelled && setDrafts(list))
      .catch(() => !cancelled && setDrafts([]));
    return () => {
      cancelled = true;
    };
  }, [selected]);

  const grouped = useMemo(() => {
    const bySubject = new Map<string, AuthorableSubtopic[]>();
    for (const subtopic of subtopics) {
      const list = bySubject.get(subtopic.subject) ?? [];
      list.push(subtopic);
      bySubject.set(subtopic.subject, list);
    }
    return [...bySubject.entries()];
  }, [subtopics]);

  const current = subtopics.find((s) => s.id === selected);

  async function onGenerate() {
    if (!selected || generating) return;
    setGenerating(true);
    setError(null);
    setNote(null);
    try {
      const result = await generateQuestions(selected, count, difficulty);
      setDrafts(result.drafts);
      setRejected(result.rejected);
      setNote(
        result.created === 0
          ? "No usable questions came back. Try again, or a different difficulty."
          : `${result.created} new draft${result.created === 1 ? "" : "s"} added.`,
      );
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Generation failed.");
    } finally {
      setGenerating(false);
    }
  }

  async function decide(draft: DraftQuestion, keep: boolean) {
    setBusyId(draft.id);
    setError(null);
    try {
      if (keep) {
        await publishDraft(draft.id);
      } else {
        await discardDraft(draft.id);
      }
      setDrafts((list) => list.filter((d) => d.id !== draft.id));
      setNote(keep ? "Question approved and added to the bank." : "Draft discarded.");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "That did not work.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      <Crumbs parts={[{ label: "My classes", to: "/teacher" }, { label: "Question bank" }]} />
      <header className="page-head">
        <p className="kicker">Teacher · authoring</p>
        <h1>Question bank</h1>
        <p>
          Draft multiple-choice questions from a subtopic's learning outcomes. Nothing here
          reaches a student until you approve it.
        </p>
      </header>

      {loading && <div className="banner banner--info">Loading your subjects…</div>}

      {!loading && subtopics.length === 0 && (
        <div className="banner banner--info" role="status">
          You have no teaching assignments, so there is nothing to write questions for.
        </div>
      )}

      {subtopics.length > 0 && (
        <section className="card" aria-label="Generate questions">
          <div className="field">
            <label className="field__label" htmlFor="subtopic">
              Subtopic
            </label>
            <select
              id="subtopic"
              className="field__input"
              value={selected}
              onChange={(event) => setSelected(event.target.value)}
            >
              {grouped.map(([subject, list]) => (
                <optgroup key={subject} label={subject}>
                  {list.map((subtopic) => (
                    <option key={subtopic.id} value={subtopic.id}>
                      {subtopic.topic} · {subtopic.name}
                      {subtopic.draft_count > 0 ? ` (${subtopic.draft_count} draft)` : ""}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>

          <div className="authoring-controls">
            <div className="field">
              <label className="field__label" htmlFor="count">
                How many
              </label>
              <input
                id="count"
                className="field__input"
                type="number"
                min={1}
                max={10}
                value={count}
                onChange={(event) => setCount(Number(event.target.value))}
              />
            </div>
            <div className="field">
              <span className="field__label">Difficulty</span>
              <div className="meta-row" role="group" aria-label="Difficulty">
                {DIFFICULTIES.map((level) => (
                  <button
                    key={level}
                    type="button"
                    className={`badge ${difficulty === level ? "badge--info" : ""}`}
                    aria-pressed={difficulty === level}
                    onClick={() => setDifficulty(level)}
                  >
                    {level}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="meta-row">
            <PushButton onClick={() => void onGenerate()} disabled={generating || !selected}>
              {generating ? "Writing questions…" : "Generate drafts"}
            </PushButton>
          </div>
        </section>
      )}

      {error && (
        <div className="banner banner--warning" role="alert">
          {error}
        </div>
      )}
      {note && !error && (
        <div className="banner banner--info" role="status">
          {note}
        </div>
      )}

      {rejected.length > 0 && (
        <div className="banner banner--warning" role="status">
          <strong>{rejected.length} discarded before you saw them.</strong> The checker
          rejected these:
          <ul>
            {rejected.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      )}

      {drafts.length > 0 && (
        <section aria-label="Draft questions">
          <div className="topics-section__head">
            <h2>
              {drafts.length} draft{drafts.length === 1 ? "" : "s"} awaiting your approval
            </h2>
            <p>
              {current ? `${current.subject} · ${current.name}. ` : ""}
              Approve to add to the bank, or discard.
            </p>
          </div>

          <div className="draft-list">
            {drafts.map((draft, index) => (
              <article key={draft.id} className="card draft-card">
                <div className="meta-row">
                  <span className="badge">Q{index + 1}</span>
                  {draft.difficulty && <span className="badge badge--info">{draft.difficulty}</span>}
                </div>
                <h3>{draft.prompt}</h3>

                <ul className="draft-options">
                  {draft.options.map((option) => {
                    const isCorrect = option.label === draft.correct_label;
                    return (
                      <li
                        key={option.label}
                        className={`draft-option ${isCorrect ? "is-correct" : ""}`}
                      >
                        <span className="draft-option__label">{option.label}</span>
                        <span>{option.text}</span>
                        {isCorrect && (
                          <span className="badge badge--ok">correct</span>
                        )}
                      </li>
                    );
                  })}
                </ul>

                {draft.explanation && <p className="progress-label">Why: {draft.explanation}</p>}

                <div className="meta-row">
                  <PushButton
                    size="sm"
                    onClick={() => void decide(draft, true)}
                    disabled={busyId === draft.id}
                  >
                    Approve
                  </PushButton>
                  <PushButton
                    variant="outline"
                    size="sm"
                    onClick={() => void decide(draft, false)}
                    disabled={busyId === draft.id}
                  >
                    Discard
                  </PushButton>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}
    </>
  );
}

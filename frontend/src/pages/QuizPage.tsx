import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { buildSubmitPayload, startAttempt, submitAttempt } from "../api/attempts";
import { getQuiz } from "../api/materials";
import type { QuizMaterial, StartAttemptResponse } from "../api/types";
import { ApiError } from "../api/types";
import { AppShell } from "../components/AppShell";
import { PushButton } from "../components/PushButton";

export function QuizPage() {
  const { topicId = "" } = useParams();
  const navigate = useNavigate();
  const [quiz, setQuiz] = useState<QuizMaterial | null>(null);
  const [attempt, setAttempt] = useState<StartAttemptResponse | null>(null);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setQuiz(null);
    setAttempt(null);
    setAnswers({});
    setIndex(0);
    setError(null);
    void (async () => {
      try {
        const [quizData, attemptData] = await Promise.all([
          getQuiz(topicId),
          startAttempt(topicId),
        ]);
        if (!cancelled) {
          setQuiz(quizData);
          setAttempt(attemptData);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Could not start quiz.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [topicId]);

  const question = quiz?.questions[index];
  const answeredCount = useMemo(() => Object.keys(answers).length, [answers]);
  const allAnswered = quiz ? answeredCount === quiz.questions.length : false;

  function selectOption(label: string) {
    if (!question) return;
    setAnswers((prev) => ({ ...prev, [question.number]: label }));
  }

  async function onSubmit() {
    if (!attempt || !quiz || !allAnswered) return;
    setBusy(true);
    setError(null);
    try {
      const result = await submitAttempt(attempt.id, buildSubmitPayload(answers));
      navigate(`/attempts/${result.id}`, { replace: true, state: { result } });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit quiz.");
      setBusy(false);
    }
  }

  return (
    <AppShell>
      {!quiz && !error && (
        <div className="center-state" role="status">
          Starting quiz…
        </div>
      )}

      {error && !quiz && (
        <div className="center-state">
          <p className="form__error" role="alert">
            {error}
          </p>
          <Link to={`/topics/${topicId}`}>
            <PushButton variant="soft">Back to lesson</PushButton>
          </Link>
        </div>
      )}

      {quiz && question && (
        <div className="stack-gap">
          <header className="page-head">
            <div>
              <p className="muted" style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)" }}>
                3.0 Quiz · Attempt {attempt?.attempt_number ?? "—"}
              </p>
              <h1 className="page-head__title">{quiz.title}</h1>
            </div>
          </header>

          <p className="quiz-progress">
            Question {index + 1} of {quiz.questions.length} · {answeredCount} answered
          </p>

          <article className="question-card">
            {question.difficulty && (
              <span className="difficulty">{question.difficulty}</span>
            )}
            <h2 className="question-card__prompt">{question.prompt}</h2>
            <div className="option-list" role="radiogroup" aria-label={`Question ${question.number}`}>
              {question.options.map((opt) => {
                const selected = answers[question.number] === opt.label;
                return (
                  <button
                    key={opt.label}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    className={`option ${selected ? "is-selected" : ""}`}
                    onClick={() => selectOption(opt.label)}
                  >
                    <span className="option__label">{opt.label}</span>
                    <span>{opt.text}</span>
                  </button>
                );
              })}
            </div>
          </article>

          {error && (
            <p className="form__error" role="alert">
              {error}
            </p>
          )}

          <div className="form__actions">
            <PushButton
              variant="outline"
              disabled={index === 0}
              onClick={() => setIndex((i) => Math.max(0, i - 1))}
            >
              Previous
            </PushButton>
            {index < quiz.questions.length - 1 ? (
              <PushButton
                color="pear"
                disabled={!answers[question.number]}
                onClick={() => setIndex((i) => i + 1)}
              >
                Next question <span className="btn__arrow">→</span>
              </PushButton>
            ) : (
              <PushButton
                color="coral"
                loading={busy}
                disabled={!allAnswered}
                onClick={() => void onSubmit()}
              >
                Submit quiz <span className="btn__arrow">→</span>
              </PushButton>
            )}
          </div>

          {!allAnswered && index === quiz.questions.length - 1 && (
            <p className="muted">Answer every question before you submit.</p>
          )}
        </div>
      )}
    </AppShell>
  );
}

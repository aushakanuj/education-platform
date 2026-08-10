import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { Crumbs } from "../../components/Crumbs";
import { PushButton } from "../../components/PushButton";
import {
  nextPolicyMessageId,
  POLICY_CHAT_DISCLAIMER,
  POLICY_CHAT_SEED,
  replyToPolicyQuestion,
  type PolicyChatMessage,
} from "../../mocks/policyChat";

export function PolicyChatPage() {
  const [messages, setMessages] = useState<PolicyChatMessage[]>(POLICY_CHAT_SEED);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || busy) return;

    const userMsg: PolicyChatMessage = {
      id: nextPolicyMessageId("user"),
      role: "user",
      content: text,
      createdAt: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setDraft("");
    setBusy(true);

    // Short delay so the mock feels like a reply, not an instant echo.
    await new Promise((resolve) => window.setTimeout(resolve, 420));

    const reply = replyToPolicyQuestion(text);
    const assistantMsg: PolicyChatMessage = {
      id: nextPolicyMessageId("assistant"),
      createdAt: new Date().toISOString(),
      ...reply,
    };
    setMessages((prev) => [...prev, assistantMsg]);
    setBusy(false);
  }

  return (
    <div className="policy-chat">
      <Crumbs parts={[{ label: "Policy assistant" }]} />
      <div className="back-row">
        <Link to="/admin/materials" className="btn btn--outline btn--sm">
          ← Back to materials
        </Link>
      </div>
      <header className="page-head">
        <p className="kicker">Administrator · policy lookup</p>
        <h1>Policy assistant</h1>
        <p>Ask about attendance, assessments, or enrollment to see fixture replies.</p>
      </header>

      <p className="muted" role="note">
        Indexed docs from{" "}
        <Link to="/admin/documents">Documents</Link> will power grounded answers later. This
        thread still uses fixtures only.
      </p>

      <p className="policy-chat__disclaimer" role="note">
        {POLICY_CHAT_DISCLAIMER}
      </p>

      <div className="policy-chat__thread" aria-live="polite">
        {messages.map((msg) => (
          <article
            key={msg.id}
            className={`policy-chat__bubble policy-chat__bubble--${msg.role}`}
          >
            <p className="policy-chat__role">{msg.role === "user" ? "You" : "Assistant"}</p>
            <p className="policy-chat__body">{msg.content}</p>
            {msg.citations && msg.citations.length > 0 && (
              <ul className="policy-chat__citations">
                {msg.citations.map((cite) => (
                  <li key={cite.id}>
                    <span className="policy-chat__cite-label">{cite.label}</span>
                    <span className="policy-chat__cite-excerpt">{cite.excerpt}</span>
                  </li>
                ))}
              </ul>
            )}
          </article>
        ))}
        {busy && (
          <p className="policy-chat__typing muted" role="status">
            Looking up fixtures…
          </p>
        )}
        <div ref={bottomRef} />
      </div>

      <form className="policy-chat__composer" onSubmit={(e) => void onSubmit(e)}>
        <label className="sr-only" htmlFor="policy-chat-input">
          Message
        </label>
        <textarea
          id="policy-chat-input"
          className="policy-chat__input"
          rows={2}
          placeholder="e.g. What is the attendance escalation policy?"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={busy}
        />
        <PushButton type="submit" disabled={busy || !draft.trim()} loading={busy}>
          Send
        </PushButton>
      </form>
    </div>
  );
}

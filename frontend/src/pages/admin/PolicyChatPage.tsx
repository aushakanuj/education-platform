import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import {
  createChat,
  deleteChat,
  getChat,
  listChats,
  postChatMessage,
  type ChatMessage,
  type ContextUsage,
  type ConversationSummary,
} from "../../api/chats";
import { Crumbs } from "../../components/Crumbs";
import { PushButton } from "../../components/PushButton";

const DISCLAIMER =
  "Answers are grounded in indexed institution documents when retrieval finds evidence. Model output is advisory — verify against published policy.";

function emptyContext(): ContextUsage {
  return { used_tokens: 0, limit_tokens: 8192, used_percent: 0 };
}

export function PolicyChatPage() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [context, setContext] = useState<ContextUsage>(emptyContext());
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadingList, setLoadingList] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const refreshList = useCallback(async () => {
    const rows = await listChats();
    setConversations(rows);
    return rows;
  }, []);

  const loadConversation = useCallback(async (id: string) => {
    const detail = await getChat(id);
    setActiveId(detail.id);
    setMessages(detail.messages);
    setContext(detail.context);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoadingList(true);
      setError(null);
      try {
        let rows = await refreshList();
        if (cancelled) return;
        if (rows.length === 0) {
          const created = await createChat();
          if (cancelled) return;
          rows = await refreshList();
          await loadConversation(created.id);
        } else {
          await loadConversation(rows[0].id);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load chats");
        }
      } finally {
        if (!cancelled) setLoadingList(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadConversation, refreshList]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy]);

  async function onNewChat() {
    setBusy(true);
    setError(null);
    try {
      const created = await createChat();
      await refreshList();
      await loadConversation(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create chat");
    } finally {
      setBusy(false);
    }
  }

  async function onSelectChat(id: string) {
    if (id === activeId || busy) return;
    setBusy(true);
    setError(null);
    try {
      await loadConversation(id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open chat");
    } finally {
      setBusy(false);
    }
  }

  async function onDeleteChat(id: string) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await deleteChat(id);
      const rows = await refreshList();
      if (rows.length === 0) {
        const created = await createChat();
        await refreshList();
        await loadConversation(created.id);
      } else {
        const next = rows.find((r) => r.id !== id) ?? rows[0];
        await loadConversation(next.id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete chat");
    } finally {
      setBusy(false);
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || busy || !activeId) return;

    setDraft("");
    setBusy(true);
    setError(null);
    const optimistic: ChatMessage = {
      id: `local-${Date.now()}`,
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimistic]);

    try {
      const result = await postChatMessage(activeId, text);
      setMessages((prev) => {
        const withoutOptimistic = prev.filter((m) => m.id !== optimistic.id);
        return [...withoutOptimistic, result.user_message, result.assistant_message];
      });
      setContext(result.context);
      await refreshList();
    } catch (err) {
      setMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
      setError(err instanceof Error ? err.message : "Send failed");
    } finally {
      setBusy(false);
    }
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
        <p className="kicker">Administrator · grounded policy lookup</p>
        <h1>Policy assistant</h1>
        <p>Multi-chat threads with retrieval over indexed Documents and a live context meter.</p>
      </header>

      <p className="policy-chat__disclaimer" role="note">
        {DISCLAIMER} Index PDFs under <Link to="/admin/documents">Documents</Link>.
      </p>

      {error && (
        <p className="banner banner--warn" role="alert">
          {error}
        </p>
      )}

      <div className="policy-chat__layout">
        <aside className="policy-chat__sidebar" aria-label="Conversations">
          <div className="policy-chat__sidebar-head">
            <h2>Chats</h2>
            <PushButton type="button" size="sm" onClick={() => void onNewChat()} disabled={busy}>
              New
            </PushButton>
          </div>
          {loadingList ? (
            <p className="muted">Loading…</p>
          ) : (
            <ul className="policy-chat__conv-list">
              {conversations.map((conv) => (
                <li key={conv.id}>
                  <button
                    type="button"
                    className={
                      conv.id === activeId
                        ? "policy-chat__conv policy-chat__conv--active"
                        : "policy-chat__conv"
                    }
                    onClick={() => void onSelectChat(conv.id)}
                    disabled={busy}
                  >
                    <span className="policy-chat__conv-title">{conv.title}</span>
                    <span className="policy-chat__conv-meta">{conv.context.used_percent}% ctx</span>
                  </button>
                  <button
                    type="button"
                    className="policy-chat__conv-delete"
                    aria-label={`Delete ${conv.title}`}
                    onClick={() => void onDeleteChat(conv.id)}
                    disabled={busy}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <div className="policy-chat__main">
          <div
            className="policy-chat__context"
            role="status"
            aria-label={`Context window ${context.used_percent} percent`}
          >
            <div className="policy-chat__context-label">
              <span>Context</span>
              <span>
                {context.used_percent}% · {context.used_tokens}/{context.limit_tokens} tokens
              </span>
            </div>
            <div className="policy-chat__context-track">
              <div
                className="policy-chat__context-fill"
                style={{ width: `${Math.min(100, Math.max(0, context.used_percent))}%` }}
              />
            </div>
          </div>

          <div className="policy-chat__thread" aria-live="polite">
            {messages.map((msg) => (
              <article
                key={msg.id}
                className={`policy-chat__bubble policy-chat__bubble--${msg.role === "user" ? "user" : "assistant"}`}
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
                Running safety checks and retrieval…
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
              disabled={busy || !activeId}
            />
            <PushButton type="submit" disabled={busy || !draft.trim() || !activeId} loading={busy}>
              Send
            </PushButton>
          </form>
        </div>
      </div>
    </div>
  );
}

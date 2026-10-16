import { useState, type FormEvent } from "react";

import { askGenerationAssistant } from "../api/generation";
import type { DraftChangeRequest } from "../api/types";
import { PushButton } from "./PushButton";

type GenerationReviewAssistantProps = {
  runId: string;
  revisionId: string;
  target: DraftChangeRequest["target"];
  disabled: boolean;
  onInsertDraft: (draft: DraftChangeRequest) => void;
};

export function GenerationReviewAssistant({
  runId,
  revisionId,
  target,
  disabled,
  onInsertDraft,
}: GenerationReviewAssistantProps) {
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reply, setReply] = useState<string | null>(null);

  async function onAsk(event: FormEvent) {
    event.preventDefault();
    const trimmed = message.trim();
    if (!trimmed || disabled || busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await askGenerationAssistant(runId, {
        revision_id: revisionId,
        target,
        message: trimmed,
      });
      setReply(result.content);
      if (result.draft_change_request) {
        onInsertDraft(result.draft_change_request);
      }
      setMessage("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Assistant is unavailable.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="outline-review__assistant" onSubmit={onAsk}>
      <p className="outline-review__sequence">Ask the review assistant</p>
      <p className="muted">
        Drafts a change request for this target. It does not submit your review.
      </p>
      <div className="form__field">
        <label className="form__label" htmlFor="review-assistant-message">
          Assistant question
        </label>
        <textarea
          id="review-assistant-message"
          className="form__input"
          rows={3}
          value={message}
          disabled={disabled || busy}
          onChange={(event) => setMessage(event.target.value)}
        />
      </div>
      <PushButton
        type="submit"
        variant="outline"
        disabled={disabled || busy || message.trim() === ""}
        loading={busy}
      >
        Ask assistant
      </PushButton>
      {error ? <p className="form__error">{error}</p> : null}
      {reply ? <p className="outline-review__assistant-reply">{reply}</p> : null}
    </form>
  );
}

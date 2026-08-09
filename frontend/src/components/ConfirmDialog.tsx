type DialogAction = {
  label: string;
  variant?: "default" | "soft" | "outline";
  onClick?: () => void;
  keepOpen?: boolean;
};

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  body: string;
  actions: DialogAction[];
  onDismiss?: () => void;
};

export function ConfirmDialog({ open, title, body, actions, onDismiss }: ConfirmDialogProps) {
  if (!open) return null;

  return (
    <div
      className={`overlay ${open ? "is-open" : ""}`}
      role="presentation"
      onClick={() => onDismiss?.()}
    >
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-body"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="confirm-dialog-title">{title}</h2>
        <p id="confirm-dialog-body">{body}</p>
        <div className="dialog__actions">
          {actions.map((action) => {
            const variantClass =
              action.variant === "soft"
                ? "btn--soft"
                : action.variant === "outline"
                  ? "btn--outline"
                  : "";
            return (
              <button
                key={action.label}
                type="button"
                className={`btn ${variantClass}`.trim()}
                onClick={() => {
                  action.onClick?.();
                  if (!action.keepOpen) onDismiss?.();
                }}
              >
                {action.label}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

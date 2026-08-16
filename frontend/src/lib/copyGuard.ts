/** Block copy, cut, and the context menu except inside form fields. */

const EDITABLE_SELECTOR =
  "input, textarea, select, [contenteditable]:not([contenteditable='false'])";

export function isEditableTarget(target: EventTarget | null): boolean {
  if (target instanceof Element) {
    return Boolean(target.closest(EDITABLE_SELECTOR));
  }
  if (target instanceof Node && target.parentElement) {
    return Boolean(target.parentElement.closest(EDITABLE_SELECTOR));
  }
  return false;
}

export function shouldBlockCopy(target: EventTarget | null): boolean {
  return !isEditableTarget(target);
}

export function installCopyGuard(root: Document | HTMLElement = document): () => void {
  const block = (event: Event) => {
    if (!shouldBlockCopy(event.target)) return;
    event.preventDefault();
  };

  const events = ["copy", "cut", "contextmenu", "selectstart"] as const;
  for (const name of events) {
    root.addEventListener(name, block);
  }
  return () => {
    for (const name of events) {
      root.removeEventListener(name, block);
    }
  };
}

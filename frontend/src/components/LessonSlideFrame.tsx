import type { ReactNode } from "react";

import { MarkdownContent } from "./MarkdownContent";

export function LessonSlideFrame({
  title,
  content,
  footer,
  ariaLabel = "Lesson",
}: {
  title: string;
  content: string;
  footer?: ReactNode;
  ariaLabel?: string;
}) {
  return (
    <article className="panel lesson-overview" aria-label={ariaLabel}>
      <div className="lesson-overview__header">
        <h2>{title}</h2>
      </div>
      <div className="lesson-overview__scroll markdown">
        <MarkdownContent>{content}</MarkdownContent>
      </div>
      {footer ? <div className="lesson-overview__footer">{footer}</div> : null}
    </article>
  );
}

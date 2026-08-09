import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkMath from "remark-math";

type MarkdownContentProps = {
  children: string;
  className?: string;
  inline?: boolean;
};

export function MarkdownContent({
  children,
  className,
  inline = false,
}: MarkdownContentProps) {
  const classes = ["markdown-content", className].filter(Boolean).join(" ");
  return (
    <div className={classes}>
      <ReactMarkdown
        remarkPlugins={[remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={
          inline
            ? {
                p: ({ children: nodes }) => <>{nodes}</>,
              }
            : undefined
        }
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}

import { Children, isValidElement, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import { Link } from "react-router-dom";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

import { normalizeMarkdownMath } from "../lib/markdownMath";
import { MermaidDiagram } from "./MermaidDiagram";

type MarkdownContentProps = {
  children: string;
  className?: string;
  inline?: boolean;
  /** In-app paths become router links. Other hrefs stay normal anchors. */
  internalLinks?: boolean;
};

function fenceLanguage(className: string | undefined): string | undefined {
  return /language-([\w-]+)/i.exec(className ?? "")?.[1]?.toLowerCase();
}

function isMermaidDiagram(node: ReactNode): boolean {
  return isValidElement(node) && node.type === MermaidDiagram;
}

function markdownComponents(inline: boolean, internalLinks: boolean): Components {
  return {
    ...(inline
      ? {
          p: ({ children: nodes }) => <>{nodes}</>,
        }
      : {}),
    ...(internalLinks
      ? {
          a({ href, children }) {
            if (href && href.startsWith("/") && !href.startsWith("//")) {
              return <Link to={href}>{children}</Link>;
            }
            return (
              <a href={href} rel="noreferrer" target="_blank">
                {children}
              </a>
            );
          },
        }
      : {}),
    pre({ children }) {
      const nested = Children.toArray(children);
      if (nested.length === 1 && isMermaidDiagram(nested[0])) {
        return nested[0];
      }
      return <pre>{children}</pre>;
    },
    table({ children }) {
      return (
        <div className="markdown-table-scroll">
          <table>{children}</table>
        </div>
      );
    },
    code({ className, children, node: _node, ...props }) {
      if (fenceLanguage(className) === "mermaid") {
        return <MermaidDiagram chart={String(children).replace(/\n$/, "")} />;
      }
      return (
        <code className={className} {...props}>
          {children}
        </code>
      );
    },
  };
}

export function MarkdownContent({
  children,
  className,
  inline = false,
  internalLinks = false,
}: MarkdownContentProps) {
  const classes = ["markdown-content", inline ? "markdown-content--inline" : "", className]
    .filter(Boolean)
    .join(" ");
  const Tag = inline ? "span" : "div";
  return (
    <Tag className={classes}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: "ignore" }]]}
        components={markdownComponents(inline, internalLinks)}
      >
        {normalizeMarkdownMath(children)}
      </ReactMarkdown>
    </Tag>
  );
}

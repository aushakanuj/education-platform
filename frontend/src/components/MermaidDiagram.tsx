import { useEffect, useState } from "react";
import mermaid from "mermaid";

let mermaidConfigured = false;
let mermaidSeq = 0;

function configureMermaid() {
  if (mermaidConfigured) return;
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: "strict",
    htmlLabels: false,
    suppressErrorRendering: true,
    theme: "neutral",
    fontFamily: "inherit",
  });
  mermaidConfigured = true;
}

/** Quote flowchart node labels that contain parentheses so mermaid can parse them. */
export function quoteFlowchartNodeLabels(source: string): string {
  if (!/^\s*(graph|flowchart)\b/i.test(source)) return source;
  return source.replace(/\[([^\]\n]+)\]/g, (bracket, inner: string) => {
    const label = inner.trim();
    if (label.startsWith('"') || label.startsWith("'")) return bracket;
    if (!label.includes("(") && !label.includes(")")) return bracket;
    return `["${label.replace(/"/g, "#quot;")}"]`;
  });
}

function svgMarkup(svg: string): string | null {
  const parsed = new DOMParser().parseFromString(svg, "image/svg+xml");
  const root = parsed.documentElement;
  if (root.tagName.toLowerCase() !== "svg") return null;
  parsed.querySelectorAll("script").forEach((node) => node.remove());
  return new XMLSerializer().serializeToString(root);
}

function removeMermaidArtifacts(id: string, host: HTMLElement | null) {
  host?.remove();
  document.getElementById(id)?.remove();
  document.getElementById(`d${id}`)?.remove();
}

export function MermaidDiagram({ chart }: { chart: string }) {
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const id = `lesson-mermaid-${++mermaidSeq}`;
    const host = document.createElement("div");
    host.setAttribute("data-mermaid-host", id);
    host.setAttribute("aria-hidden", "true");
    host.style.position = "absolute";
    host.style.left = "-9999px";
    host.style.width = "640px";
    document.body.appendChild(host);

    configureMermaid();
    setSvg(null);
    setFailed(false);

    void (async () => {
      try {
        const source = quoteFlowchartNodeLabels(chart);
        const parsed = await mermaid.parse(source, { suppressErrors: true });
        if (!parsed) {
          if (!cancelled) setFailed(true);
          return;
        }
        const { svg: rendered } = await mermaid.render(id, source, host);
        if (cancelled) return;
        const markup = svgMarkup(rendered);
        if (!markup) {
          setFailed(true);
          return;
        }
        setSvg(markup);
      } catch {
        if (!cancelled) setFailed(true);
      } finally {
        removeMermaidArtifacts(id, host);
      }
    })();

    return () => {
      cancelled = true;
      removeMermaidArtifacts(id, host);
    };
  }, [chart]);

  return (
    <div
      className="markdown-mermaid mermaid"
      role="img"
      aria-label="Diagram"
      aria-busy={svg === null && !failed}
    >
      {failed ? (
        <p className="markdown-mermaid__error">Could not render this diagram.</p>
      ) : svg ? (
        <div dangerouslySetInnerHTML={{ __html: svg }} />
      ) : (
        <span className="sr-only">Loading diagram</span>
      )}
    </div>
  );
}

const FENCED_BLOCK = /(```[\s\S]*?```)/g;
const UNDECODED_FORMULA = /<!--\s*formula-not-decoded\s*-->/gi;
const WRAPPING_MARKDOWN_FENCE = /^```(?:markdown|md)[ \t]*\n([\s\S]*)\n```[ \t]*$/i;

function unescapeLatexBody(body: string): string {
  return body.replace(/\\\\/g, "\\");
}

function tightenDollarMath(markdown: string): string {
  let text = markdown.replace(/\$\$([\s\S]*?)\$\$/g, (_match, body: string) => {
    const inner = unescapeLatexBody(body.trim());
    return inner ? `$$${inner}$$` : "";
  });
  return text.replace(/\$([^$\n]+?)\$/g, (_match, body: string) => {
    const inner = unescapeLatexBody(body.trim());
    return inner ? `$${inner}$` : "";
  });
}

function convertEscapedDelimiters(markdown: string): string {
  let text = markdown.replace(
    /\\{1,2}\[([\s\S]*?)\\{1,2}\]/g,
    (_match, body: string) => `$$${unescapeLatexBody(body.trim())}$$`,
  );
  return text.replace(
    /\\{1,2}\(([\s\S]*?)\\{1,2}\)/g,
    (_match, body: string) => `$${unescapeLatexBody(body.trim())}$`,
  );
}

function normalizeMathInProse(markdown: string): string {
  let text = markdown.replace(UNDECODED_FORMULA, "");
  text = convertEscapedDelimiters(text);
  text = text.replace(
    /(^|\n)[ \t]*\$\$([\s\S]*?)\$\$[ \t]*(?=\n|$)/g,
    (_match, lead: string, body: string) => `${lead}\n\n$$${unescapeLatexBody(body.trim())}$$\n\n`,
  );
  return tightenDollarMath(text);
}

/** Strip a document-level ```markdown wrapper without touching inner fences. */
export function unwrapMarkdownFence(markdown: string): string {
  const trimmed = markdown.replace(/\r\n/g, "\n").trim();
  const match = WRAPPING_MARKDOWN_FENCE.exec(trimmed);
  return match ? match[1] : markdown.replace(/\r\n/g, "\n");
}

/** Make Docling / LLM math delimiters parseable by remark-math + KaTeX. */
export function normalizeMarkdownMath(markdown: string): string {
  return unwrapMarkdownFence(markdown)
    .split(FENCED_BLOCK)
    .map((part) => (part.startsWith("```") ? part : normalizeMathInProse(part)))
    .join("");
}

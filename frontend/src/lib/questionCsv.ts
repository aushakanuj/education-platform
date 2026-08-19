import type { DraftQuestion } from "../api/authoring";

const HEADERS = [
  "subject",
  "topic",
  "subtopic",
  "prompt",
  "option_a",
  "option_b",
  "option_c",
  "option_d",
  "correct",
  "explanation",
  "difficulty",
];

/**
 * One CSV field, quoted only when it has to be.
 *
 * A question prompt is free text a model wrote: it can hold commas, quotation marks and
 * newlines, any of which splits a naive export into the wrong number of columns. RFC 4180
 * says quote the field and double any quote inside it, which is what every spreadsheet
 * expects on the way back in.
 */
function field(value: string | null | undefined): string {
  const text = value ?? "";
  if (!/[",\r\n]/.test(text)) return text;
  return `"${text.replaceAll('"', '""')}"`;
}

export type CsvContext = { subject: string; topic: string; subtopic: string };

/** The approved bank as a spreadsheet: one question per row, options in fixed columns. */
export function questionsToCsv(questions: DraftQuestion[], context: CsvContext): string {
  const rows = questions.map((question) => {
    const text = (label: string) =>
      question.options.find((option) => option.label === label)?.text ?? "";
    return [
      context.subject,
      context.topic,
      context.subtopic,
      question.prompt,
      text("A"),
      text("B"),
      text("C"),
      text("D"),
      question.correct_label ?? "",
      question.explanation ?? "",
      question.difficulty ?? "",
    ]
      .map(field)
      .join(",");
  });

  // Trailing newline: some tools drop the final row without one.
  return [HEADERS.join(","), ...rows].join("\r\n") + "\r\n";
}

/** "Mathematics · Fractions" -> "mathematics-fractions-questions.csv". */
export function csvFilename(context: CsvContext): string {
  const slug = `${context.subject}-${context.subtopic}`
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
  return `${slug}-questions.csv`;
}

/**
 * Hand the file to the browser.
 *
 * Built and revoked here rather than pointing an anchor at the API: the export needs the
 * caller's bearer token, and a plain link cannot carry one. A URL that returned answer
 * keys without a token would be the leak.
 */
export function downloadCsv(filename: string, csv: string): void {
  // The BOM is what makes Excel read UTF-8 rather than the local codepage; without it,
  // Arabic student and subject names arrive as mojibake.
  const blob = new Blob(["﻿", csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

import { describe, expect, it } from "vitest";

import { csvFilename, questionsToCsv } from "./questionCsv";
import type { DraftQuestion } from "../api/authoring";

const CONTEXT = { subject: "Mathematics", topic: "Number", subtopic: "Fractions" };

function question(over: Partial<DraftQuestion> = {}): DraftQuestion {
  return {
    id: "q1",
    prompt: "What is 3/4 + 1/4?",
    options: [
      { label: "A", text: "1" },
      { label: "B", text: "1/2" },
      { label: "C", text: "2/4" },
      { label: "D", text: "5/4" },
    ],
    correct_label: "A",
    explanation: "The denominators match, so add the numerators.",
    difficulty: "easy",
    ...over,
  };
}

function rows(csv: string): string[] {
  return csv.trimEnd().split("\r\n");
}

/**
 * Minimal RFC 4180 reader, so the tests check what a spreadsheet would actually read back
 * rather than what the string happens to look like. Counting raw commas is not the same
 * question: a correctly quoted field is allowed to contain as many as it likes.
 */
function parseFields(row: string): string[] {
  const fields: string[] = [];
  let current = "";
  let quoted = false;

  for (let i = 0; i < row.length; i += 1) {
    const char = row[i];
    if (quoted) {
      if (char === '"' && row[i + 1] === '"') {
        current += '"';
        i += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        current += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      fields.push(current);
      current = "";
    } else {
      current += char;
    }
  }
  fields.push(current);
  return fields;
}

describe("questionsToCsv", () => {
  it("writes a header and one row per question", () => {
    const csv = questionsToCsv([question(), question({ id: "q2" })], CONTEXT);
    expect(rows(csv)).toHaveLength(3);
    expect(rows(csv)[0]).toBe(
      "subject,topic,subtopic,prompt,option_a,option_b,option_c,option_d,correct,explanation,difficulty",
    );
  });

  it("carries the context and the correct answer", () => {
    const row = rows(questionsToCsv([question()], CONTEXT))[1];
    expect(row).toContain("Mathematics,Number,Fractions");
    expect(row).toContain(",A,");
  });

  it("quotes a prompt containing a comma so the columns do not shift", () => {
    const csv = questionsToCsv([question({ prompt: "Add 1/2, then simplify" })], CONTEXT);
    const fields = parseFields(rows(csv)[1]);
    expect(fields).toHaveLength(parseFields(rows(csv)[0]).length);
    expect(fields[3]).toBe("Add 1/2, then simplify");
  });

  it("doubles a quotation mark inside a field, as RFC 4180 requires", () => {
    const csv = questionsToCsv([question({ prompt: 'Which is a "unit" fraction?' })], CONTEXT);
    expect(rows(csv)[1]).toContain('"Which is a ""unit"" fraction?"');
    expect(parseFields(rows(csv)[1])[3]).toBe('Which is a "unit" fraction?');
  });

  it("survives a newline inside a prompt", () => {
    const csv = questionsToCsv([question({ prompt: "Line one\nLine two" })], CONTEXT);
    expect(csv).toContain('"Line one\nLine two"');
  });

  it("writes an empty cell for an option the question does not have", () => {
    const csv = questionsToCsv(
      [question({ options: [{ label: "A", text: "1" }] })],
      CONTEXT,
    );
    expect(rows(csv)[1]).toContain("1,,,");
  });

  it("writes empty cells rather than the word null for missing fields", () => {
    const csv = questionsToCsv([question({ explanation: null, difficulty: null })], CONTEXT);
    expect(rows(csv)[1]).not.toContain("null");
  });

  it("still emits the header when there is nothing to export", () => {
    expect(rows(questionsToCsv([], CONTEXT))).toHaveLength(1);
  });
});

describe("csvFilename", () => {
  it("builds a safe filename from the subject and subtopic", () => {
    expect(csvFilename(CONTEXT)).toBe("mathematics-fractions-questions.csv");
  });

  it("collapses punctuation rather than putting it in a filename", () => {
    expect(csvFilename({ ...CONTEXT, subtopic: "Ratio & Proportion" })).toBe(
      "mathematics-ratio-proportion-questions.csv",
    );
  });
});

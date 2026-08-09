import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MarkdownContent } from "./MarkdownContent";

describe("MarkdownContent", () => {
  it("renders LaTeX math instead of raw dollar signs", () => {
    render(<MarkdownContent>{"Area is $n^2$ square units."}</MarkdownContent>);
    expect(screen.queryByText(/\$n\^2\$/)).not.toBeInTheDocument();
    expect(document.querySelector(".katex")).not.toBeNull();
    expect(screen.getByText(/Area is/)).toBeInTheDocument();
    expect(screen.getByText(/square units/)).toBeInTheDocument();
  });
});

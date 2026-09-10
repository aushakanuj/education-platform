import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AtRiskPage } from "./AtRiskPage";
import type { AtRiskFlag } from "../../api/atRisk";

vi.mock("../../api/atRisk", () => ({
  fetchAtRiskFlags: vi.fn(),
  dismissAtRiskFlag: vi.fn(),
}));

import { dismissAtRiskFlag, fetchAtRiskFlags } from "../../api/atRisk";

function flag(over: Partial<AtRiskFlag> = {}): AtRiskFlag {
  return {
    id: "flag-1",
    student_id: "s1",
    student_name: "Aisha Rahman",
    grade_subject_offering_id: "gso-1",
    subject: "Mathematics",
    tier: "urgent",
    drivers: [
      { metric: "mastery_percent", value: 56, comparison: "below 60.0", window: "single reading" },
      {
        metric: "mastery_trend",
        value: 22.5,
        comparison: "declined 22.5 points (threshold 15.0)",
        window: "last 3 attempts vs earlier",
      },
    ],
    status: "active",
    dismissed_by_user_id: null,
    dismissal_note: null,
    ...over,
  };
}

function renderPage() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AtRiskPage />
    </MemoryRouter>,
  );
}

describe("AtRiskPage", () => {
  beforeEach(() => {
    vi.mocked(fetchAtRiskFlags).mockReset();
    vi.mocked(dismissAtRiskFlag).mockReset();
  });

  it("lists a teacher's flags with the tier and the named reasons, including the actual values", async () => {
    vi.mocked(fetchAtRiskFlags).mockResolvedValue({ rows_returned: 1, items: [flag()] });
    renderPage();

    expect(await screen.findByText("Aisha Rahman")).toBeInTheDocument();
    const row = screen.getByRole("row", { name: /Aisha Rahman/ });
    expect(within(row).getByText("Mathematics")).toBeInTheDocument();
    expect(within(row).getByText("urgent")).toBeInTheDocument();
    // Not just "below 60.0" -- the student's actual measured value must be stated too.
    expect(row.textContent).toContain("Mastery: 56.0% (below 60.0)");
    expect(row.textContent).toContain("Mastery trend: declined 22.5 points (threshold 15.0)");
    expect(row.textContent).toContain("last 3 attempts vs earlier");
  });

  it("filters by tier and narrows the count shown on each tier button", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchAtRiskFlags).mockResolvedValue({
      rows_returned: 2,
      items: [
        flag({ id: "f1", student_name: "Aisha Rahman", tier: "urgent" }),
        flag({
          id: "f2",
          student_name: "Hassan Nair",
          tier: "monitor",
          drivers: [
            { metric: "mastery_percent", value: 55, comparison: "below 60.0", window: "single reading" },
          ],
        }),
      ],
    });
    renderPage();
    await screen.findByText("Aisha Rahman");
    expect(screen.getByText("Hassan Nair")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Urgent (1)" }));

    expect(screen.getByText("Aisha Rahman")).toBeInTheDocument();
    expect(screen.queryByText("Hassan Nair")).not.toBeInTheDocument();
  });

  it("finds a flag by the student's name", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchAtRiskFlags).mockResolvedValue({
      rows_returned: 2,
      items: [
        flag({ id: "f1", student_name: "Aisha Rahman" }),
        flag({ id: "f2", student_name: "Hassan Nair" }),
      ],
    });
    renderPage();
    await screen.findByText("Aisha Rahman");

    await user.type(screen.getByLabelText("Find a student"), "Hassan");

    expect(screen.queryByText("Aisha Rahman")).not.toBeInTheDocument();
    expect(screen.getByText("Hassan Nair")).toBeInTheDocument();
  });

  it("says so plainly when a search matches nobody, without hiding the tier controls", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchAtRiskFlags).mockResolvedValue({ rows_returned: 1, items: [flag()] });
    renderPage();
    await screen.findByText("Aisha Rahman");

    await user.type(screen.getByLabelText("Find a student"), "Nobody");

    expect(screen.getByText(/No flag matches/)).toBeInTheDocument();
    expect(screen.getByLabelText("Find a student")).toBeInTheDocument();
  });

  it("says so plainly when nobody in the teacher's classes is flagged", async () => {
    vi.mocked(fetchAtRiskFlags).mockResolvedValue({ rows_returned: 0, items: [] });
    renderPage();

    expect(await screen.findByText(/Nobody in your classes is flagged/)).toBeInTheDocument();
  });

  it("shows the server's error rather than a blank page", async () => {
    vi.mocked(fetchAtRiskFlags).mockRejectedValue(new Error("Session expired."));
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("Session expired.");
  });

  it("dismisses a flag with a note and removes it from the list", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchAtRiskFlags).mockResolvedValue({ rows_returned: 1, items: [flag()] });
    vi.mocked(dismissAtRiskFlag).mockResolvedValue({ ...flag(), status: "dismissed" });
    renderPage();
    await screen.findByText("Aisha Rahman");

    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/Note/), "Spoke with the student.");
    await user.click(within(dialog).getByRole("button", { name: "Dismiss" }));

    expect(dismissAtRiskFlag).toHaveBeenCalledWith("flag-1", "Spoke with the student.");
    expect(await screen.findByText(/Dismissed Aisha Rahman's flag/)).toBeInTheDocument();
    expect(screen.queryByText("Aisha Rahman")).not.toBeInTheDocument();
  });

  it("lets a dismissal go through with no note at all", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchAtRiskFlags).mockResolvedValue({ rows_returned: 1, items: [flag()] });
    vi.mocked(dismissAtRiskFlag).mockResolvedValue({ ...flag(), status: "dismissed" });
    renderPage();
    await screen.findByText("Aisha Rahman");

    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Dismiss" }));

    expect(dismissAtRiskFlag).toHaveBeenCalledWith("flag-1", "");
  });
});

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AdminAtRiskPage } from "./AdminAtRiskPage";
import type { AtRiskFlag } from "../../api/atRisk";

vi.mock("../../api/atRisk", () => ({
  fetchAtRiskFlags: vi.fn(),
  dismissAtRiskFlag: vi.fn(),
  recomputeAtRisk: vi.fn(),
}));

import { dismissAtRiskFlag, fetchAtRiskFlags, recomputeAtRisk } from "../../api/atRisk";

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
    ],
    status: "active",
    dismissed_by_user_id: null,
    dismissal_note: null,
    ...over,
  };
}

function attendanceFlag(over: Partial<AtRiskFlag> = {}): AtRiskFlag {
  return flag({
    id: "flag-2",
    student_name: "Bilal Farsi",
    grade_subject_offering_id: null,
    subject: null,
    tier: "monitor",
    drivers: [
      { metric: "attendance_percent", value: 70, comparison: "below 80.0", window: "single reading" },
    ],
    ...over,
  });
}

function renderPage() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AdminAtRiskPage />
    </MemoryRouter>,
  );
}

describe("AdminAtRiskPage", () => {
  beforeEach(() => {
    vi.mocked(fetchAtRiskFlags).mockReset();
    vi.mocked(dismissAtRiskFlag).mockReset();
    vi.mocked(recomputeAtRisk).mockReset();
  });

  it("lists both subject flags and whole-student attendance-only flags, with real values", async () => {
    vi.mocked(fetchAtRiskFlags).mockResolvedValue({
      rows_returned: 2,
      items: [flag(), attendanceFlag()],
    });
    renderPage();

    expect(await screen.findByText("Aisha Rahman")).toBeInTheDocument();
    const attendanceRow = screen.getByRole("row", { name: /Bilal Farsi/ });
    expect(within(attendanceRow).getByText("Attendance")).toBeInTheDocument();
    expect(attendanceRow.textContent).toContain("Attendance: 70.0% (below 80.0)");
  });

  it("filters the school-wide list by tier", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchAtRiskFlags).mockResolvedValue({
      rows_returned: 2,
      items: [flag(), attendanceFlag()],
    });
    renderPage();
    await screen.findByText("Aisha Rahman");

    await user.click(screen.getByRole("button", { name: "Monitor (1)" }));

    expect(screen.queryByText("Aisha Rahman")).not.toBeInTheDocument();
    expect(screen.getByText("Bilal Farsi")).toBeInTheDocument();
  });

  it("recomputes and reports the result, then refreshes the list", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchAtRiskFlags)
      .mockResolvedValueOnce({ rows_returned: 0, items: [] })
      .mockResolvedValueOnce({ rows_returned: 1, items: [flag()] });
    vi.mocked(recomputeAtRisk).mockResolvedValue({
      students_considered: 240,
      flags_active: 185,
      flags_resolved: 3,
    });
    renderPage();
    await screen.findByText(/No active flags/);

    await user.click(screen.getByRole("button", { name: /Recompute now/ }));

    expect(await screen.findByText(/Checked 240 students: 185 active flags, 3 resolved/))
      .toBeInTheDocument();
    expect(await screen.findByText("Aisha Rahman")).toBeInTheDocument();
    expect(fetchAtRiskFlags).toHaveBeenCalledTimes(2);
  });

  it("reports a recompute failure without losing the current list", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchAtRiskFlags).mockResolvedValue({ rows_returned: 1, items: [flag()] });
    vi.mocked(recomputeAtRisk).mockRejectedValue(new Error("Only administrators can do that."));
    renderPage();
    await screen.findByText("Aisha Rahman");

    await user.click(screen.getByRole("button", { name: /Recompute now/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Only administrators can do that.");
    expect(screen.getByText("Aisha Rahman")).toBeInTheDocument();
  });

  it("dismisses a flag from the school-wide list", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchAtRiskFlags).mockResolvedValue({ rows_returned: 1, items: [flag()] });
    vi.mocked(dismissAtRiskFlag).mockResolvedValue({ ...flag(), status: "dismissed" });
    renderPage();
    await screen.findByText("Aisha Rahman");

    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Dismiss" }));

    expect(dismissAtRiskFlag).toHaveBeenCalledWith("flag-1", "");
    expect(screen.queryByText("Aisha Rahman")).not.toBeInTheDocument();
  });
});

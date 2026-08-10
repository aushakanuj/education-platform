import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "./AppShell";

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({
    user: { full_name: "Asha Student" },
    enrollments: {
      grade_enrollments: [{ status: "active", grade_name: "Grade 8" }],
      subject_enrollments: [{ status: "active", subject_name: "Mathematics" }],
    },
    enrolled: true,
    signOut: vi.fn(),
  }),
}));

vi.mock("../api/demo", () => ({
  resetDemoProgress: vi.fn(),
}));

describe("AppShell", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("uses Subjects / School material navigation from the mock", () => {
    render(
      <MemoryRouter
        initialEntries={["/subjects/sub-1"]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route
            path="/subjects/:subjectId"
            element={
              <AppShell subjectTitle="Mathematics">
                <div>Subject body</div>
              </AppShell>
            }
          />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getAllByRole("link", { name: /Subjects/ }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: /Mathematics/ }).length).toBeGreaterThan(0);
    expect(screen.getByText("Asha Student")).toBeInTheDocument();
    expect(screen.getAllByText(/Grade 8 · Demo School/).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Reset demo" })).toBeInTheDocument();
    expect(screen.queryByText(/1\.0 Enroll/)).not.toBeInTheDocument();
    expect(screen.queryByText(/2\.0 Study/)).not.toBeInTheDocument();
  });

  it("collapses and expands the primary rail", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <MemoryRouter
        initialEntries={["/subjects/sub-1"]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route
            path="/subjects/:subjectId"
            element={
              <AppShell subjectTitle="Mathematics">
                <div>Subject body</div>
              </AppShell>
            }
          />
        </Routes>
      </MemoryRouter>,
    );

    const toggle = screen.getByRole("button", { name: "Collapse navigation" });
    await user.click(toggle);

    expect(container.querySelector(".rail.is-collapsed")).not.toBeNull();
    expect(container.querySelector(".app.is-rail-collapsed")).not.toBeNull();
    expect(window.localStorage.getItem("ep.railCollapsed")).toBe("1");

    await user.click(screen.getByRole("button", { name: "Expand navigation" }));
    expect(container.querySelector(".rail.is-collapsed")).toBeNull();
    expect(window.localStorage.getItem("ep.railCollapsed")).toBe("0");
  });
});

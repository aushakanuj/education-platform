import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { AppShell } from "./AppShell";

const signOut = vi.fn();

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({
    user: { full_name: "Asha Student" },
    enrollments: {
      grade_enrollments: [{ status: "active", grade_name: "Grade 8" }],
      subject_enrollments: [{ status: "active", subject_name: "Mathematics" }],
    },
    enrolled: true,
    signOut,
  }),
}));

vi.mock("../api/demo", () => ({
  resetDemoProgress: vi.fn(),
}));

function renderShell() {
  return render(
    <MemoryRouter
      initialEntries={["/subjects/sub-1"]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route
          path="/subjects/:subjectId"
          element={
            <AppShell>
              <div>Subject body</div>
            </AppShell>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("AppShell", () => {
  it("shows the persistent sidebar with Home and Feedback navigation", () => {
    renderShell();

    const rail = screen.getByRole("complementary", { name: "Primary" });
    expect(rail).toBeInTheDocument();
    expect(within(rail).getByRole("link", { name: "Home" })).toBeInTheDocument();
    expect(within(rail).getByRole("link", { name: "Feedback" })).toBeInTheDocument();
  });
});

import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

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

describe("AppShell", () => {
  it("uses Subjects / Current topic navigation from the mock", () => {
    render(
      <MemoryRouter
        initialEntries={["/subjects/sub-1/topics/topic-1"]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route
            path="/subjects/:subjectId/topics/:topicId"
            element={
              <AppShell topicTitle="Approved Materials">
                <div>Topic body</div>
              </AppShell>
            }
          />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getAllByRole("link", { name: "Subjects" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "Approved Materials" }).length).toBeGreaterThan(0);
    expect(screen.getByText("Asha Student")).toBeInTheDocument();
    expect(screen.getAllByText(/Grade 8 · Demo School/).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Reset demo" })).toBeInTheDocument();
    expect(screen.queryByText(/1\.0 Enroll/)).not.toBeInTheDocument();
    expect(screen.queryByText(/2\.0 Study/)).not.toBeInTheDocument();
  });
});

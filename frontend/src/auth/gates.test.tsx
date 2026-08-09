import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { RequireAuth } from "../auth/RequireAuth";
import { RequireEnrollment } from "../auth/RequireEnrollment";

const authState = vi.hoisted(() => ({
  user: null as null | { id: string },
  enrolled: false,
  loading: false,
}));

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({
    user: authState.user,
    enrolled: authState.enrolled,
    loading: authState.loading,
  }),
}));

function renderGates(initial: string) {
  return render(
    <MemoryRouter
      initialEntries={[initial]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route path="/login" element={<div>Login page</div>} />
        <Route path="/enroll" element={<div>Enroll page</div>} />
        <Route
          path="/home"
          element={
            <RequireAuth>
              <RequireEnrollment>
                <div>Home page</div>
              </RequireEnrollment>
            </RequireAuth>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("route gates", () => {
  it("redirects unauthenticated users to login", () => {
    authState.user = null;
    authState.enrolled = false;
    authState.loading = false;
    renderGates("/home");
    expect(screen.getByText("Login page")).toBeInTheDocument();
  });

  it("redirects authenticated but unenrolled users to enroll", () => {
    authState.user = { id: "u1" };
    authState.enrolled = false;
    authState.loading = false;
    renderGates("/home");
    expect(screen.getByText("Enroll page")).toBeInTheDocument();
  });

  it("allows enrolled users through", () => {
    authState.user = { id: "u1" };
    authState.enrolled = true;
    authState.loading = false;
    renderGates("/home");
    expect(screen.getByText("Home page")).toBeInTheDocument();
  });
});

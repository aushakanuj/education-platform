import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { RequireAuth } from "../auth/RequireAuth";
import { RequireEnrollment } from "../auth/RequireEnrollment";
import { RequireRole } from "../auth/RequireRole";
import {
  hasRole,
  primaryRole,
  ROLE_ADMIN,
  ROLE_STUDENT,
  ROLE_TEACHER,
  roleHome,
} from "../auth/roles";

const authState = vi.hoisted(() => ({
  user: null as null | { id: string; roles: string[] },
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
        <Route path="/admin" element={<div>Admin home</div>} />
        <Route path="/teacher" element={<div>Teacher home</div>} />
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
        <Route
          path="/admin-area"
          element={
            <RequireAuth>
              <RequireRole roles={ROLE_ADMIN}>
                <div>Admin only</div>
              </RequireRole>
            </RequireAuth>
          }
        />
        <Route
          path="/teacher-area"
          element={
            <RequireAuth>
              <RequireRole roles={ROLE_TEACHER}>
                <div>Teacher only</div>
              </RequireRole>
            </RequireAuth>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("role helpers", () => {
  it("hasRole checks membership", () => {
    expect(hasRole([ROLE_STUDENT], ROLE_STUDENT)).toBe(true);
    expect(hasRole([ROLE_STUDENT], ROLE_ADMIN)).toBe(false);
  });

  it("primaryRole prefers admin over teacher over student", () => {
    expect(primaryRole([ROLE_STUDENT, ROLE_TEACHER, ROLE_ADMIN])).toBe(ROLE_ADMIN);
    expect(primaryRole([ROLE_STUDENT, ROLE_TEACHER])).toBe(ROLE_TEACHER);
    expect(primaryRole([ROLE_STUDENT])).toBe(ROLE_STUDENT);
    expect(primaryRole([])).toBeNull();
  });

  it("roleHome maps primary role to path", () => {
    expect(roleHome([ROLE_ADMIN])).toBe("/admin");
    expect(roleHome([ROLE_TEACHER])).toBe("/teacher");
    expect(roleHome([ROLE_STUDENT])).toBe("/");
    expect(roleHome([])).toBe("/");
  });
});

describe("route gates", () => {
  it("redirects unauthenticated users to login", () => {
    authState.user = null;
    authState.enrolled = false;
    authState.loading = false;
    renderGates("/home");
    expect(screen.getByText("Login page")).toBeInTheDocument();
  });

  it("redirects authenticated but unenrolled users to enroll", () => {
    authState.user = { id: "u1", roles: [ROLE_STUDENT] };
    authState.enrolled = false;
    authState.loading = false;
    renderGates("/home");
    expect(screen.getByText("Enroll page")).toBeInTheDocument();
  });

  it("allows enrolled users through", () => {
    authState.user = { id: "u1", roles: [ROLE_STUDENT] };
    authState.enrolled = true;
    authState.loading = false;
    renderGates("/home");
    expect(screen.getByText("Home page")).toBeInTheDocument();
  });

  it("sends administrators away from student enrollment gate to /admin", () => {
    authState.user = { id: "a1", roles: [ROLE_ADMIN] };
    authState.enrolled = false;
    authState.loading = false;
    renderGates("/home");
    expect(screen.getByText("Admin home")).toBeInTheDocument();
  });

  it("RequireRole allows matching role", () => {
    authState.user = { id: "a1", roles: [ROLE_ADMIN] };
    authState.loading = false;
    renderGates("/admin-area");
    expect(screen.getByText("Admin only")).toBeInTheDocument();
  });

  it("RequireRole redirects wrong role to their home", () => {
    authState.user = { id: "t1", roles: [ROLE_TEACHER] };
    authState.loading = false;
    renderGates("/admin-area");
    expect(screen.getByText("Teacher home")).toBeInTheDocument();
  });

  it("RequireRole redirects unauthenticated to login", () => {
    authState.user = null;
    authState.loading = false;
    renderGates("/teacher-area");
    expect(screen.getByText("Login page")).toBeInTheDocument();
  });
});

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import * as authApi from "../api/auth";
import { clearTokens, getAccessToken } from "../api/client";
import {
  fetchEnrollments,
  hasActiveSubjectEnrollment,
} from "../api/enrollments";
import type { EnrollmentSummary, MeResponse } from "../api/types";
import { ApiError } from "../api/types";
import {
  hasRole as rolesInclude,
  primaryRole as resolvePrimaryRole,
  ROLE_ADMIN,
  ROLE_TEACHER,
  type AppRole,
} from "./roles";

/** localStorage key for DEV-only fixture admin/teacher sessions (no real JWT). */
export const DEV_MOCK_ROLE_KEY = "ep_dev_mock_role";

type AuthState = {
  user: MeResponse | null;
  enrollments: EnrollmentSummary | null;
  enrolled: boolean;
  loading: boolean;
  /** True when the session is a DEV fixture (admin/teacher mock), not a real JWT. */
  isDevMockSession: boolean;
  hasRole: (role: string) => boolean;
  primaryRole: AppRole | null;
  refreshProfile: () => Promise<void>;
  signIn: (email: string, password: string) => Promise<void>;
  createStudent: (input: {
    email: string;
    password: string;
    full_name: string;
    student_identifier: string;
  }) => Promise<void>;
  signOut: () => Promise<void>;
  setEnrollments: (summary: EnrollmentSummary) => void;
  /**
   * DEV-only: install a fixture MeResponse for administrator or teacher so mock
   * UIs can be explored without seeded backend accounts. Persists via localStorage.
   */
  enterDevRoleSession: (role: typeof ROLE_ADMIN | typeof ROLE_TEACHER) => void;
};

const AuthContext = createContext<AuthState | null>(null);

function readDevMockRole(): typeof ROLE_ADMIN | typeof ROLE_TEACHER | null {
  if (!import.meta.env.DEV) return null;
  try {
    const raw = localStorage.getItem(DEV_MOCK_ROLE_KEY);
    if (raw === ROLE_ADMIN || raw === ROLE_TEACHER) return raw;
  } catch {
    /* ignore */
  }
  return null;
}

function clearDevMockRole(): void {
  try {
    localStorage.removeItem(DEV_MOCK_ROLE_KEY);
  } catch {
    /* ignore */
  }
}

function writeDevMockRole(role: typeof ROLE_ADMIN | typeof ROLE_TEACHER): void {
  try {
    localStorage.setItem(DEV_MOCK_ROLE_KEY, role);
  } catch {
    /* ignore */
  }
}

function fixtureUserForRole(
  role: typeof ROLE_ADMIN | typeof ROLE_TEACHER,
): MeResponse {
  const isAdmin = role === ROLE_ADMIN;
  return {
    id: isAdmin ? "dev-admin" : "dev-teacher",
    email: isAdmin ? "admin@demo.school" : "teacher@demo.school",
    full_name: isAdmin ? "Dev Administrator" : "Dev Teacher",
    institution_id: "dev-institution",
    roles: [role],
    student_profile_id: null,
    status: "active",
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<MeResponse | null>(null);
  const [enrollments, setEnrollmentsState] = useState<EnrollmentSummary | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [isDevMockSession, setIsDevMockSession] = useState(false);

  const loadSession = useCallback(async () => {
    const mockRole = readDevMockRole();
    if (mockRole) {
      clearTokens();
      setUser(fixtureUserForRole(mockRole));
      setEnrollmentsState(null);
      setIsDevMockSession(true);
      setLoading(false);
      return;
    }

    setIsDevMockSession(false);
    if (!getAccessToken()) {
      setUser(null);
      setEnrollmentsState(null);
      setLoading(false);
      return;
    }
    try {
      const me = await authApi.fetchMe();
      setUser(me);
      try {
        const summary = await fetchEnrollments();
        setEnrollmentsState(summary);
      } catch {
        setEnrollmentsState(null);
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearTokens();
      }
      setUser(null);
      setEnrollmentsState(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSession();
  }, [loadSession]);

  const signIn = useCallback(async (email: string, password: string) => {
    setLoading(true);
    try {
      clearDevMockRole();
      setIsDevMockSession(false);
      await authApi.login({ email, password });
      const me = await authApi.fetchMe();
      setUser(me);
      const summary = await fetchEnrollments();
      setEnrollmentsState(summary);
    } finally {
      setLoading(false);
    }
  }, []);

  const createStudent = useCallback(
    async (input: {
      email: string;
      password: string;
      full_name: string;
      student_identifier: string;
    }) => {
      setLoading(true);
      try {
        clearDevMockRole();
        setIsDevMockSession(false);
        await authApi.provisionStudent(input);
        await authApi.login({ email: input.email, password: input.password });
        const me = await authApi.fetchMe();
        setUser(me);
        const summary = await fetchEnrollments();
        setEnrollmentsState(summary);
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  const signOut = useCallback(async () => {
    const wasMock = isDevMockSession || readDevMockRole() != null;
    clearDevMockRole();
    setIsDevMockSession(false);
    if (wasMock || !getAccessToken()) {
      // Mock sessions have no refresh token; still clear any stale tokens.
      clearTokens();
      setUser(null);
      setEnrollmentsState(null);
      return;
    }
    await authApi.logout();
    setUser(null);
    setEnrollmentsState(null);
  }, [isDevMockSession]);

  const setEnrollments = useCallback((summary: EnrollmentSummary) => {
    setEnrollmentsState(summary);
  }, []);

  const enterDevRoleSession = useCallback(
    (role: typeof ROLE_ADMIN | typeof ROLE_TEACHER) => {
      if (!import.meta.env.DEV) {
        throw new Error("enterDevRoleSession is only available in DEV");
      }
      clearTokens();
      writeDevMockRole(role);
      setUser(fixtureUserForRole(role));
      setEnrollmentsState(null);
      setIsDevMockSession(true);
      setLoading(false);
    },
    [],
  );

  const hasRoleFn = useCallback(
    (role: string) => (user ? rolesInclude(user.roles, role) : false),
    [user],
  );

  const primary = useMemo(
    () => (user ? resolvePrimaryRole(user.roles) : null),
    [user],
  );

  const value = useMemo<AuthState>(
    () => ({
      user,
      enrollments,
      enrolled: enrollments ? hasActiveSubjectEnrollment(enrollments) : false,
      loading,
      isDevMockSession,
      hasRole: hasRoleFn,
      primaryRole: primary,
      refreshProfile: loadSession,
      signIn,
      createStudent,
      signOut,
      setEnrollments,
      enterDevRoleSession,
    }),
    [
      user,
      enrollments,
      loading,
      isDevMockSession,
      hasRoleFn,
      primary,
      loadSession,
      signIn,
      createStudent,
      signOut,
      setEnrollments,
      enterDevRoleSession,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}

export {
  hasRole,
  primaryRole,
  roleHome,
  ROLE_ADMIN,
  ROLE_TEACHER,
  ROLE_STUDENT,
} from "./roles";
export type { AppRole } from "./roles";

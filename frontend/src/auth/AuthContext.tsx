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

type AuthState = {
  user: MeResponse | null;
  enrollments: EnrollmentSummary | null;
  enrolled: boolean;
  loading: boolean;
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
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<MeResponse | null>(null);
  const [enrollments, setEnrollmentsState] = useState<EnrollmentSummary | null>(
    null,
  );
  const [loading, setLoading] = useState(true);

  const loadSession = useCallback(async () => {
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
    await authApi.logout();
    setUser(null);
    setEnrollmentsState(null);
  }, []);

  const setEnrollments = useCallback((summary: EnrollmentSummary) => {
    setEnrollmentsState(summary);
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      enrollments,
      enrolled: enrollments ? hasActiveSubjectEnrollment(enrollments) : false,
      loading,
      refreshProfile: loadSession,
      signIn,
      createStudent,
      signOut,
      setEnrollments,
    }),
    [
      user,
      enrollments,
      loading,
      loadSession,
      signIn,
      createStudent,
      signOut,
      setEnrollments,
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

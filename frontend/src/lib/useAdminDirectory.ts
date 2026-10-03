import { useCallback, useEffect, useRef, useState } from "react";

import { fetchLearningDirectory } from "../api/materials";
import { ApiError } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import {
  adaptLearningDirectory,
  getAdminGrade,
  getAdminSubject,
  getAdminTopic,
  MOCK_SESSION_MATERIALS_ERROR,
  type AdminGrade,
  type AdminSubject,
  type AdminTopic,
} from "./adminCurriculumLive";

export type UseAdminDirectoryResult = {
  grades: AdminGrade[] | null;
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
  getGrade: (gradeKey: string) => AdminGrade | undefined;
  getSubject: (
    gradeKey: string,
    subjectId: string,
  ) => { grade: AdminGrade; subject: AdminSubject } | undefined;
  getTopic: (
    gradeKey: string,
    subjectId: string,
    topicId: string,
  ) => { grade: AdminGrade; subject: AdminSubject; topic: AdminTopic } | undefined;
};

export function useAdminDirectory(): UseAdminDirectoryResult {
  const { isDevMockSession } = useAuth();
  const [grades, setGrades] = useState<AdminGrade[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);
  const loadedOnceRef = useRef(false);

  const reload = useCallback(async () => {
    if (isDevMockSession) {
      setGrades(null);
      setError(MOCK_SESSION_MATERIALS_ERROR);
      setLoading(false);
      return;
    }

    const requestId = ++requestIdRef.current;
    if (!loadedOnceRef.current) setLoading(true);
    try {
      const directory = await fetchLearningDirectory();
      if (requestId !== requestIdRef.current) return;
      setGrades(adaptLearningDirectory(directory));
      setError(null);
      loadedOnceRef.current = true;
    } catch (err) {
      if (requestId !== requestIdRef.current) return;
      setGrades(null);
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not load curriculum directory.",
      );
    } finally {
      if (requestId === requestIdRef.current) setLoading(false);
    }
  }, [isDevMockSession]);

  useEffect(() => {
    void reload();
    return () => {
      requestIdRef.current += 1;
    };
  }, [reload]);

  return {
    grades,
    loading,
    error,
    reload,
    getGrade: (gradeKey) => (grades ? getAdminGrade(grades, gradeKey) : undefined),
    getSubject: (gradeKey, subjectId) =>
      grades ? getAdminSubject(grades, gradeKey, subjectId) : undefined,
    getTopic: (gradeKey, subjectId, topicId) =>
      grades ? getAdminTopic(grades, gradeKey, subjectId, topicId) : undefined,
  };
}

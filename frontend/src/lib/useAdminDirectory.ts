import { useEffect, useState } from "react";

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

  useEffect(() => {
    let cancelled = false;

    if (isDevMockSession) {
      setGrades(null);
      setError(MOCK_SESSION_MATERIALS_ERROR);
      setLoading(false);
      return;
    }

    setLoading(true);
    void (async () => {
      try {
        const directory = await fetchLearningDirectory();
        if (cancelled) return;
        setGrades(adaptLearningDirectory(directory));
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setGrades(null);
        setError(
          err instanceof ApiError
            ? err.message
            : "Could not load curriculum directory.",
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [isDevMockSession]);

  return {
    grades,
    loading,
    error,
    getGrade: (gradeKey) => (grades ? getAdminGrade(grades, gradeKey) : undefined),
    getSubject: (gradeKey, subjectId) =>
      grades ? getAdminSubject(grades, gradeKey, subjectId) : undefined,
    getTopic: (gradeKey, subjectId, topicId) =>
      grades ? getAdminTopic(grades, gradeKey, subjectId, topicId) : undefined,
  };
}

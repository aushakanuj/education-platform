import { useEffect, useState } from "react";

import { fetchLearningDirectory } from "../api/materials";
import type { LearningDirectory } from "../api/types";

export type LearningDirectoryState = {
  directory: LearningDirectory | null;
  loading: boolean;
  error: string | null;
};

export function useLearningDirectory(): LearningDirectoryState {
  const [directory, setDirectory] = useState<LearningDirectory | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchLearningDirectory()
      .then((data) => {
        if (cancelled) return;
        setDirectory(data);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setDirectory(null);
        setError(err instanceof Error ? err.message : "Could not load materials.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { directory, loading, error };
}

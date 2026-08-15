import { useEffect, useState } from "react";

import { fetchLearningDirectory } from "../api/materials";
import type { LearningDirectory } from "../api/types";
import { ApiError } from "../api/types";

let cache: LearningDirectory | null = null;

export function clearLearningDirectoryCache(): void {
  cache = null;
}

/** Cached like subtopic lessons so subject chrome can paint on the first frame after navigation. */
export function useLearningDirectory() {
  const [directory, setDirectory] = useState<LearningDirectory | null>(cache);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (cache) {
      setDirectory(cache);
    }
    void (async () => {
      try {
        const data = await fetchLearningDirectory();
        if (cancelled) return;
        cache = data;
        setDirectory(data);
        setError(null);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Could not load subjects.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return { directory, error };
}

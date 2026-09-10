import { useCallback, useEffect, useState } from "react";

import { fetchAtRiskFlags, type AtRiskFlag } from "../api/atRisk";

export type AtRiskFlagsState = {
  loading: boolean;
  error: string | null;
  flags: AtRiskFlag[];
  /** Removes a flag from the list without a round trip -- used right after a dismiss. */
  removeFlag: (flagId: string) => void;
  /** Re-fetches from the server -- used after a recompute changes what exists. */
  refresh: () => Promise<void>;
};

/** Active at-risk flags for the signed-in teacher or administrator, already narrowed by
 * their Scope server-side. Shared by both the teacher and admin pages so the loading/error
 * handling and the post-dismiss/post-recompute update behaviour stay identical. */
export function useAtRiskFlags(): AtRiskFlagsState {
  const [flags, setFlags] = useState<AtRiskFlag[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const page = await fetchAtRiskFlags();
      setFlags(page.items);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not load at-risk flags.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const removeFlag = useCallback((flagId: string) => {
    setFlags((current) => current.filter((flag) => flag.id !== flagId));
  }, []);

  return { loading, error, flags, removeFlag, refresh };
}

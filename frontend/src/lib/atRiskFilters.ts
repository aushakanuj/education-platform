import type { AtRiskFlag } from "../api/atRisk";

export type AtRiskTierFilter = "all" | AtRiskFlag["tier"];

export function filterAtRiskFlags(
  flags: AtRiskFlag[],
  tier: AtRiskTierFilter,
  query: string,
): AtRiskFlag[] {
  const needle = query.trim().toLowerCase();
  return flags.filter((flag) => {
    if (tier !== "all" && flag.tier !== tier) return false;
    if (needle && !flag.student_name.toLowerCase().includes(needle)) return false;
    return true;
  });
}

export type AtRiskTierCounts = Record<AtRiskTierFilter, number>;

/** A school-wide recompute can produce well over a hundred flags -- these counts are what
 * make the tier filter buttons and the summary line honest rather than guessed. */
export function countByTier(flags: AtRiskFlag[]): AtRiskTierCounts {
  const counts: AtRiskTierCounts = { all: flags.length, monitor: 0, attention: 0, urgent: 0 };
  for (const flag of flags) {
    counts[flag.tier] += 1;
  }
  return counts;
}

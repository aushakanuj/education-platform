import { countByTier, type AtRiskTierFilter } from "../lib/atRiskFilters";
import type { AtRiskFlag } from "../api/atRisk";

const TIERS: [AtRiskTierFilter, string][] = [
  ["all", "All"],
  ["urgent", "Urgent"],
  ["attention", "Attention"],
  ["monitor", "Monitor"],
];

type AtRiskFilterBarProps = {
  flags: AtRiskFlag[];
  tier: AtRiskTierFilter;
  query: string;
  onTierChange: (tier: AtRiskTierFilter) => void;
  onQueryChange: (query: string) => void;
};

/** Search + tier filter, shared by the teacher and admin at-risk pages -- same shape as
 * RosterPage's own "Find a student" + sort controls, so it feels like the same app. Mostly
 * a convenience for the admin view, where a school-wide recompute can produce well over a
 * hundred rows to scan through. */
export function AtRiskFilterBar({ flags, tier, query, onTierChange, onQueryChange }: AtRiskFilterBarProps) {
  const counts = countByTier(flags);

  return (
    <div className="roster-controls">
      <div className="field">
        <label className="field__label" htmlFor="at-risk-search">
          Find a student
        </label>
        <input
          id="at-risk-search"
          className="field__input"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="Name"
        />
      </div>
      <div className="field">
        <span className="field__label">Tier</span>
        <div className="meta-row" role="group" aria-label="Filter by tier">
          {TIERS.map(([key, text]) => (
            <button
              key={key}
              type="button"
              className={`badge ${tier === key ? "badge--info" : ""}`}
              aria-pressed={tier === key}
              onClick={() => onTierChange(key)}
            >
              {text} ({counts[key]})
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

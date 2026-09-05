import type { AtRiskFlag } from "../api/atRisk";

const BADGE_CLASS: Record<AtRiskFlag["tier"], string> = {
  urgent: "badge badge--warn",
  attention: "badge badge--info",
  monitor: "badge",
};

export function AtRiskTierBadge({ tier }: { tier: AtRiskFlag["tier"] }) {
  return <span className={BADGE_CLASS[tier]}>{tier}</span>;
}

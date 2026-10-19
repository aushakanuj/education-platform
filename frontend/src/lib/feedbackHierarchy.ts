import type {
  FeedbackAttemptScore,
  FeedbackBadge,
  FeedbackBand,
  FeedbackTrend,
  GoalOut,
} from "../api/types";

export function scoreNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  const number = typeof value === "string" ? Number(value) : value;
  return Number.isFinite(number) ? number : null;
}

/** "just" only when the student is within 10 points of the topic goal. */
export function focusSentence(gapPercent: number, topicName: string): string {
  if (gapPercent <= 10) {
    return `You're just ${gapPercent}% from your goal on ${topicName}.`;
  }
  return `${gapPercent}% to go to reach your goal on ${topicName}.`;
}

/** Minutes from a stored duration. Missing durations stay off the page. */
export function formatDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  if (minutes < 1) return "Under a minute";
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (rest === 0) return `${hours} h`;
  return `${hours} h ${rest} min`;
}

export function formatScore(value: string | number | null | undefined): string {
  const number = scoreNumber(value);
  if (number === null) return "Not attempted";
  return `${Math.round(number)}%`;
}

/** Short tile value. The sign is a minus, not a hyphen, so it stays one line. */
export function formatPointChange(delta: string | number | null | undefined): string | null {
  const number = scoreNumber(delta);
  if (number === null) return null;
  const points = Math.abs(Math.round(number));
  if (points === 0) return "0 pts";
  return number > 0 ? `+${points} pts` : `−${points} pts`;
}

/** One phrase. A missing trend stays blank instead of "declining · -100%". */
export function formatTrend(
  trend: FeedbackTrend,
  delta: string | number | null | undefined,
): string | null {
  if (trend === null || delta === null || delta === undefined) return null;
  const points = Math.abs(Math.round(scoreNumber(delta) ?? 0));
  if (points === 0 || trend === "flat") return "No change since the previous attempt";
  switch (trend) {
    case "improving":
      return `Up ${points} points since the previous attempt`;
    case "declining":
      return `Down ${points} points since the previous attempt`;
    default: {
      const unreachable: never = trend;
      return unreachable;
    }
  }
}

export function badgeLabel(badge: FeedbackBadge): string {
  switch (badge) {
    case "not_attempted":
      return "Not attempted";
    case "passed":
      return "Passed";
    case "keep_going":
      return "Keep going";
    default: {
      const unreachable: never = badge;
      return unreachable;
    }
  }
}

export type AttemptTitle = { label: string; emoji: string; color: string };

/** Same titles and colours the old subtopic cards used, earned by the topic quiz. */
export function attemptTitle(attempts: number, bestScore: number): AttemptTitle {
  const band: "perfect" | "high" | "pass" =
    bestScore === 100 ? "perfect" : bestScore >= 90 ? "high" : "pass";
  const titles: Record<typeof band, AttemptTitle[]> = {
    perfect: [
      { label: "Flawless", emoji: "👑", color: "#92400e" },
      { label: "Diamond", emoji: "💎", color: "#0e7490" },
      { label: "Tenacious", emoji: "🏅", color: "#7c3aed" },
      { label: "Champion", emoji: "🥇", color: "#b45309" },
      { label: "Legendary", emoji: "🏆", color: "#be185d" },
    ],
    high: [
      { label: "Star Performer", emoji: "🌟", color: "#166534" },
      { label: "Sharp Mind", emoji: "🔥", color: "#991b1b" },
      { label: "Rising Star", emoji: "🚀", color: "#1e40af" },
      { label: "Breakthrough", emoji: "💡", color: "#b45309" },
      { label: "Hard Earned", emoji: "⭐", color: "#7c3aed" },
    ],
    pass: [
      { label: "First Try!", emoji: "🎯", color: "#166534" },
      { label: "Quick Learner", emoji: "⚡", color: "#1e40af" },
      { label: "Persistent", emoji: "💪", color: "#7c3aed" },
      { label: "Determined", emoji: "🔄", color: "#b45309" },
      { label: "Never Give Up", emoji: "🌱", color: "#be185d" },
    ],
  };
  return titles[band][Math.min(Math.max(attempts, 1) - 1, 4)];
}

export function attemptBadge(
  badge: FeedbackBadge,
  attemptCount: number,
  best: string | number | null | undefined,
): string {
  return attemptBadgePresentation(badge, attemptCount, best).text;
}

export function attemptBadgePresentation(
  badge: FeedbackBadge,
  attemptCount: number,
  best: string | number | null | undefined,
): { text: string; color: string | null } {
  if (badge === "not_attempted") return { text: "Not attempted", color: null };
  const score = scoreNumber(best);
  if (score === null || badge === "keep_going" || score < 70) {
    return { text: "Keep going", color: null };
  }
  const title = attemptTitle(attemptCount, score);
  return { text: `${title.emoji} ${title.label}`, color: title.color };
}

/** Mean gain from each topic's first scored attempt to its latest. */
export function momentumGain(scores: FeedbackAttemptScore[][]): number | null {
  const gains: number[] = [];
  for (const series of scores) {
    const ordered = [...series].sort((left, right) => left.attempt_number - right.attempt_number);
    if (ordered.length < 2) continue;
    const first = scoreNumber(ordered[0]?.score_percent);
    const latest = scoreNumber(ordered[ordered.length - 1]?.score_percent);
    if (first === null || latest === null) continue;
    gains.push(latest - first);
  }
  if (gains.length === 0) return null;
  return Math.round(gains.reduce((sum, gain) => sum + gain, 0) / gains.length);
}

export function goalStatusLabel(
  goal: Pick<GoalOut, "status" | "target_percent">,
  best: string | number | null,
): "Achieved ✓" | "Missed" | "On track" {
  const latest = scoreNumber(best);
  const target = scoreNumber(goal.target_percent) ?? 0;
  const status = latest !== null && latest >= target ? "achieved" : goal.status;
  switch (status) {
    case "achieved":
      return "Achieved ✓";
    case "missed":
      return "Missed";
    case "on_track":
      return "On track";
    default: {
      const unreachable: never = status;
      return unreachable;
    }
  }
}

export function achievementCopy(
  tier: "mastery" | "advanced" | "proficient" | "on_track",
): { emoji: string; label: string; detail: string } {
  switch (tier) {
    case "mastery":
      return {
        emoji: "🏆",
        label: "Mastery!",
        detail: "Perfect score — you've completely nailed this subject!",
      };
    case "advanced":
      return {
        emoji: "🔥",
        label: "Advanced!",
        detail: "Excellent work — you're well above the bar!",
      };
    case "proficient":
      return {
        emoji: "⭐",
        label: "Proficient!",
        detail: "Solid understanding across all concepts!",
      };
    case "on_track":
      return {
        emoji: "🌱",
        label: "On Track!",
        detail: "You're passing — keep pushing to go higher!",
      };
    default: {
      const unreachable: never = tier;
      return unreachable;
    }
  }
}

type ConfidenceLevel = "still_learning" | "getting_it" | "confident";

/** Topic rows the subject self-check may name. Concept names are not accepted. */
export type CalibrationTopic = {
  name: string;
  percent: number | null;
};

function joinNames(names: string[]): string {
  if (names.length <= 1) return names[0] ?? "";
  if (names.length === 2) return `${names[0]} and ${names[1]}`;
  return `${names.slice(0, -1).join(", ")}, and ${names[names.length - 1]}`;
}

function are(names: string[]): string {
  return names.length === 1 ? "is" : "are";
}

/**
 * Subject-level self-check note. Names topics that are under 70%, never concepts.
 * Wording matches `subject_calibration` in the backend analysis module.
 */
export function calibrationMessage(
  confidence: ConfidenceLevel,
  topics: CalibrationTopic[],
): string {
  const scored = topics.filter((topic): topic is CalibrationTopic & { percent: number } => topic.percent !== null);
  const well = scored
    .filter((topic) => topic.percent >= 70)
    .sort((left, right) => right.percent - left.percent || left.name.localeCompare(right.name));
  const focus = scored
    .filter((topic) => topic.percent < 70)
    .sort((left, right) => left.percent - right.percent || left.name.localeCompare(right.name))
    .slice(0, 3);
  const named = focus.map((topic) => topic.name);
  switch (confidence) {
    case "confident":
      if (named.length > 0) {
        return `You said Confident, but ${joinNames(named)} ${are(named)} under 70%.`;
      }
      if (well.length > 0) {
        return "You said Confident, and the topics you have tried are at 70% or above.";
      }
      return "You said Confident. A topic quiz will show how that lines up.";
    case "still_learning":
      if (well.length > 0 && named.length === 0) {
        return "You said Still learning, but the topics you have tried are at 70% or above.";
      }
      if (named.length > 0) {
        return `You said Still learning, and ${joinNames(named)} ${are(named)} under 70%.`;
      }
      return "You said Still learning. A topic quiz will show how that lines up.";
    case "getting_it":
      if (named.length > 0) {
        return `You said Getting it. ${joinNames(named)} ${are(named)} under 70%.`;
      }
      if (well.length > 0) {
        return "You said Getting it, and the topics you have tried are at 70% or above.";
      }
      return "You said Getting it. A topic quiz will show how that lines up.";
    default: {
      const unreachable: never = confidence;
      return unreachable;
    }
  }
}

export function bandLabel(band: FeedbackBand): string {
  switch (band) {
    case "strong":
      return "Strong";
    case "okay":
      return "Okay";
    case "needs_work":
      return "Needs work";
    default: {
      const unreachable: never = band;
      return unreachable;
    }
  }
}

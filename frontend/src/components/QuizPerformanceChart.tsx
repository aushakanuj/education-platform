import type { AttemptHistoryItem } from "../api/types";

type Point = {
  id: string;
  label: string;
  score: number;
  passed: boolean | null;
};

function scoredAttempts(attempts: AttemptHistoryItem[]): Point[] {
  return [...attempts]
    .filter(
      (attempt) =>
        attempt.score_percent != null &&
        attempt.status !== "in_progress" &&
        attempt.status !== "abandoned",
    )
    .sort((a, b) => a.attempt_number - b.attempt_number)
    .map((attempt) => ({
      id: attempt.id,
      label: `#${attempt.attempt_number}`,
      score: Math.round(Number(attempt.score_percent)),
      passed: attempt.passed,
    }));
}

export function QuizPerformanceChart({
  attempts,
  passThreshold = 70,
}: {
  attempts: AttemptHistoryItem[];
  passThreshold?: number;
}) {
  const points = scoredAttempts(attempts);
  const threshold = Math.round(Number(passThreshold));

  if (points.length === 0) {
    return (
      <div className="quiz-chart quiz-chart--empty" role="img" aria-label="No quiz scores yet">
        <p>No scored attempts yet. Take the quiz to see performance over time.</p>
      </div>
    );
  }

  const width = 720;
  const height = 220;
  const padL = 36;
  const padR = 40;
  const padT = 24;
  const padB = 26;
  const chartW = width - padL - padR;
  const chartH = height - padT - padB;
  const maxScore = 100;
  const gridScores = [0, 25, 50, 75, 100];
  // Keep first/last points inset so score labels don't collide with axes.
  const xInset = points.length === 1 ? 0 : Math.min(chartW * 0.04, 18);

  function yFor(score: number) {
    return padT + chartH - (score / maxScore) * chartH;
  }

  const coords = points.map((point, index) => {
    const usable = chartW - xInset * 2;
    const x =
      points.length === 1
        ? padL + chartW / 2
        : padL + xInset + (index / (points.length - 1)) * usable;
    return { ...point, x, y: yFor(point.score) };
  });

  const linePath = coords
    .map((c, i) => `${i === 0 ? "M" : "L"} ${c.x.toFixed(1)} ${c.y.toFixed(1)}`)
    .join(" ");
  const areaPath =
    coords.length > 0
      ? [
          `M ${coords[0].x.toFixed(1)} ${yFor(0).toFixed(1)}`,
          ...coords.map((c) => `L ${c.x.toFixed(1)} ${c.y.toFixed(1)}`),
          `L ${coords[coords.length - 1].x.toFixed(1)} ${yFor(0).toFixed(1)}`,
          "Z",
        ].join(" ")
      : "";
  const thresholdY = yFor(threshold);
  const best = Math.max(...points.map((p) => p.score));
  const latest = points[points.length - 1];

  return (
    <div className="quiz-chart">
      <div className="quiz-chart__head">
        <div>
          <h3 className="quiz-chart__title">Performance over time</h3>
          <p className="quiz-chart__summary">
            Latest {latest.score}% · Best {best}% · {points.length} attempt
            {points.length === 1 ? "" : "s"}
          </p>
        </div>
        <div className="quiz-chart__legend" aria-hidden="true">
          <span className="quiz-chart__legend-item">
            <span className="quiz-chart__swatch quiz-chart__swatch--pass" /> Pass
          </span>
          <span className="quiz-chart__legend-item">
            <span className="quiz-chart__swatch quiz-chart__swatch--fail" /> Not passed
          </span>
          <span className="quiz-chart__legend-item">
            <span className="quiz-chart__swatch quiz-chart__swatch--pass-line" /> {threshold}% pass
          </span>
        </div>
      </div>
      <svg
        className="quiz-chart__svg"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`Quiz scores across ${points.length} attempt${points.length === 1 ? "" : "s"}. Latest ${latest.score} percent, best ${best} percent.`}
      >
        {gridScores.map((score) => {
          const y = yFor(score);
          return (
            <g key={score}>
              <line
                className="quiz-chart__grid"
                x1={padL}
                y1={y}
                x2={padL + chartW}
                y2={y}
              />
              <text className="quiz-chart__axis" x={padL - 10} y={y + 4} textAnchor="end">
                {score}
              </text>
            </g>
          );
        })}

        <line
          className="quiz-chart__threshold"
          x1={padL}
          y1={thresholdY}
          x2={padL + chartW}
          y2={thresholdY}
          strokeDasharray="5 4"
        />
        <text
          className="quiz-chart__threshold-label"
          x={padL + chartW + 8}
          y={thresholdY + 4}
          textAnchor="start"
        >
          {threshold}%
        </text>

        {coords.length > 1 && <path className="quiz-chart__area" d={areaPath} />}
        {coords.length > 1 && <path className="quiz-chart__line" d={linePath} fill="none" />}

        {coords.map((point) => {
          // Place score above the point; if near the top, put it below instead.
          const scoreAbove = point.y > padT + 18;
          const scoreY = scoreAbove ? point.y - 14 : point.y + 20;
          return (
            <g key={point.id}>
              <circle
                className={`quiz-chart__dot ${point.passed ? "is-pass" : "is-fail"}`}
                cx={point.x}
                cy={point.y}
                r={6.5}
              />
              <text
                className={`quiz-chart__score quiz-chart__score-halo ${point.passed ? "is-pass" : "is-fail"}`}
                x={point.x}
                y={scoreY}
                textAnchor="middle"
              >
                {point.score}%
              </text>
              <text
                className={`quiz-chart__score ${point.passed ? "is-pass" : "is-fail"}`}
                x={point.x}
                y={scoreY}
                textAnchor="middle"
              >
                {point.score}%
              </text>
              <text className="quiz-chart__label" x={point.x} y={height - 10} textAnchor="middle">
                {point.label}
              </text>
              <title>
                Attempt {point.label}: {point.score}%
                {point.passed ? " · passed" : " · not passed"}
              </title>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

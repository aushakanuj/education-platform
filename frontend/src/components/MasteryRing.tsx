type MasteryRingProps = {
  /** null renders an empty, neutral ring -- "no data yet", not "zero percent". */
  percent: number | null;
  size?: number;
  label?: string;
};

/** A small radial progress ring. Colour follows the same strong/average/struggling
 * language as the rest of the app's badges, so a teacher reads the tone before the number. */
export function MasteryRing({ percent, size = 84, label }: MasteryRingProps) {
  const stroke = 8;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = percent === null ? 0 : Math.max(0, Math.min(100, percent));
  const offset = circumference * (1 - clamped / 100);
  const tone =
    percent === null
      ? "mastery-ring--none"
      : clamped >= 70
        ? "mastery-ring--strong"
        : clamped >= 50
          ? "mastery-ring--average"
          : "mastery-ring--struggling";

  return (
    <div className={`mastery-ring ${tone}`} style={{ width: size, height: size }}>
      <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} aria-hidden="true">
        <circle
          className="mastery-ring__track"
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={stroke}
          fill="none"
        />
        <circle
          className="mastery-ring__value"
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={stroke}
          fill="none"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <div className="mastery-ring__label">
        <strong>{percent === null ? "—" : `${Math.round(percent)}%`}</strong>
        {label && <span>{label}</span>}
      </div>
    </div>
  );
}

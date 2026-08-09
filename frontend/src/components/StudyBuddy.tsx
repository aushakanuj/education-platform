type StudyBuddyProps = {
  size?: "md" | "lg";
  className?: string;
};

export function StudyBuddy({ size = "md", className = "" }: StudyBuddyProps) {
  return (
    <span
      className={`study-buddy ${size === "lg" ? "study-buddy--lg" : ""} ${className}`.trim()}
      aria-hidden="true"
    >
      <span className="study-buddy__mouth" />
    </span>
  );
}

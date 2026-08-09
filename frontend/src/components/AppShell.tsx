import { Link } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { PushButton } from "./PushButton";
import { StageRail, type Stage } from "./StageRail";
import { StudyBuddy } from "./StudyBuddy";

const STAGES: Stage[] = [
  { id: "enroll", num: "1.0", label: "Enroll", to: "/enroll" },
  { id: "study", num: "2.0", label: "Study", to: "/" },
  { id: "quiz", num: "3.0", label: "Quiz", to: "/" },
  { id: "result", num: "4.0", label: "Result", to: "/" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, enrollments, enrolled, signOut } = useAuth();
  const grade = enrollments?.grade_enrollments.find((g) => g.status === "active");
  const subject = enrollments?.subject_enrollments.find(
    (s) => s.status === "active",
  );

  const stages: Stage[] = STAGES.map((s) => {
    if (s.id === "enroll") {
      return { ...s, done: enrolled, to: enrolled ? "/" : "/enroll" };
    }
    if (!enrolled && s.id !== "enroll") {
      return { ...s, to: "/enroll" };
    }
    return s;
  });

  return (
    <div className="app-shell">
      <aside className="app-shell__rail" aria-label="Primary">
        <Link to="/" className="app-shell__brand">
          <StudyBuddy />
          Education Platform
        </Link>
        <StageRail stages={stages} />
        <div className="app-shell__user">
          <div className="app-shell__user-name">{user?.full_name ?? "Student"}</div>
          <div className="app-shell__user-meta">
            {grade?.grade_name ?? "—"}
            {subject ? ` · ${subject.subject_name}` : ""}
          </div>
          <PushButton variant="outline" size="sm" onClick={() => void signOut()}>
            Sign out
          </PushButton>
        </div>
      </aside>

      <div className="app-shell__top">
        <div className="app-shell__top-row">
          <Link to="/" className="app-shell__brand">
            <StudyBuddy />
            Education Platform
          </Link>
          <PushButton variant="outline" size="sm" onClick={() => void signOut()}>
            Sign out
          </PushButton>
        </div>
        <StageRail stages={stages} horizontal />
      </div>

      <main className="app-shell__main">{children}</main>
    </div>
  );
}

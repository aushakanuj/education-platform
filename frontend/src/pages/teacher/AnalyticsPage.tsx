import { useState } from "react";
import { Link } from "react-router-dom";

import { ClassHeatmap } from "../../components/ClassHeatmap";
import { Crumbs } from "../../components/Crumbs";
import { MasteryRing } from "../../components/MasteryRing";
import { StudentDotGrid } from "../../components/StudentDotGrid";
import { useAtRiskFlags } from "../../lib/useAtRiskFlags";
import {
  computeHeatmap,
  computeSectionAnalytics,
  TIER_BASIS,
  type PerformanceTier,
  type SectionAnalytics,
  type TierStudent,
} from "../../lib/teacherAnalytics";
import { useTeacherClasses } from "../../lib/useTeacherClasses";

function round(value: number | null): string {
  return value === null ? "—" : `${Math.round(value)}%`;
}

const TIER_DOT: Record<PerformanceTier, string> = {
  strong: "dot--strong",
  average: "dot--average",
  struggling: "dot--struggling",
  not_started: "dot--none",
};

const TIER_LABEL: Record<PerformanceTier, string> = {
  strong: "strong",
  average: "average",
  struggling: "struggling",
  not_started: "not started",
};

const TIER_ORDER: PerformanceTier[] = ["strong", "average", "struggling", "not_started"];

/** Strongest first, so the dot grid reads as the shape of the class from best to worst. */
function orderedStudents(studentsByTier: SectionAnalytics["studentsByTier"]): TierStudent[] {
  return TIER_ORDER.flatMap((tier) => studentsByTier[tier]);
}

/**
 * A class as its students: one square each, plus counts that open into names.
 *
 * The counts stay clickable because "who are those 14" is the question the grid provokes
 * and cannot answer on its own -- a square tells you someone is there, not which someone.
 */
function ClassComposition({
  sectionId,
  distribution,
  studentsByTier,
}: {
  sectionId: string;
  distribution: SectionAnalytics["distribution"];
  studentsByTier: SectionAnalytics["studentsByTier"];
}) {
  const [openTier, setOpenTier] = useState<PerformanceTier | null>(null);
  const students = orderedStudents(studentsByTier);
  if (students.length === 0) return null;

  return (
    <div>
      <StudentDotGrid sectionId={sectionId} students={students} />
      <div className="distribution-bar__legend">
        {TIER_ORDER.map((tier) =>
          distribution[tier] > 0 ? (
            <button
              key={tier}
              type="button"
              className={`chip chip--button ${openTier === tier ? "is-active" : ""}`}
              onClick={() => setOpenTier(openTier === tier ? null : tier)}
              aria-expanded={openTier === tier}
            >
              <i className={`dot ${TIER_DOT[tier]}`} />
              {distribution[tier]} {TIER_LABEL[tier]}
            </button>
          ) : null,
        )}
      </div>
      {openTier && (
        <div className="tier-drilldown">
          <p className="progress-label">{TIER_BASIS[openTier]}</p>
          <ul className="list">
            {studentsByTier[openTier].map((student) => (
              <li className="list-item" key={student.studentId}>
                <Link
                  className="list-item__title"
                  to={`/teacher/classes/${sectionId}/students/${student.studentId}`}
                >
                  {student.fullName}
                </Link>
                <span className="badge">
                  {student.mastery === null ? "—" : `${Math.round(student.mastery)}%`}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function SectionPanel({ section }: { section: SectionAnalytics }) {
  const { atRiskCounts } = section;
  return (
    <section className="panel analytics-panel analytics-section-panel">
      <div className="analytics-section-panel__head">
        <MasteryRing percent={section.averageMastery} label="mastery" />
        <div>
          <h2>
            {section.gradeName} · {section.sectionName}
          </h2>
          <p className="progress-label">
            {section.academicPeriod} · {section.studentCount} student
            {section.studentCount === 1 ? "" : "s"} · attendance {round(section.averageAttendance)}
          </p>
          {atRiskCounts.total > 0 && (
            <div className="meta-row">
              {atRiskCounts.urgent > 0 && (
                <span className="badge badge--warn">{atRiskCounts.urgent} urgent</span>
              )}
              {atRiskCounts.attention > 0 && (
                <span className="badge badge--info">{atRiskCounts.attention} attention</span>
              )}
              {atRiskCounts.monitor > 0 && <span className="badge">{atRiskCounts.monitor} monitor</span>}
              <Link className="badge" to="/teacher/at-risk">
                See at-risk flags →
              </Link>
            </div>
          )}
        </div>
      </div>

      <ClassComposition
        sectionId={section.sectionId}
        distribution={section.distribution}
        studentsByTier={section.studentsByTier}
      />

      {section.lowAttendance.length > 0 && (
        <div>
          <p className="progress-label">Below 75% attendance</p>
          <ul className="list">
            {section.lowAttendance.map((student) => (
              <li className="list-item" key={student.studentId}>
                <span className="list-item__num" aria-hidden="true">
                  !
                </span>
                <Link
                  className="list-item__title"
                  to={`/teacher/classes/${section.sectionId}/students/${student.studentId}`}
                >
                  {student.fullName}
                </Link>
                <span className="badge badge--warn">{Math.round(student.attendancePercent)}%</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

export function AnalyticsPage() {
  const { loading: classesLoading, error: classesError, classes, scopeDescription } =
    useTeacherClasses();
  const { loading: flagsLoading, flags } = useAtRiskFlags();

  const loading = classesLoading || flagsLoading;
  const sections = computeSectionAnalytics(classes, flags);
  const heatmap = computeHeatmap(classes);

  const totalStudents = classes.reduce((sum, entry) => sum + entry.students.length, 0);
  const overallMastery =
    sections.filter((s) => s.averageMastery !== null).length > 0
      ? sections.reduce((sum, s) => sum + (s.averageMastery ?? 0), 0) /
        sections.filter((s) => s.averageMastery !== null).length
      : null;
  const overallAttendance =
    sections.filter((s) => s.averageAttendance !== null).length > 0
      ? sections.reduce((sum, s) => sum + (s.averageAttendance ?? 0), 0) /
        sections.filter((s) => s.averageAttendance !== null).length
      : null;
  const totalAtRisk = sections.reduce((sum, s) => sum + s.atRiskCounts.total, 0);

  return (
    <div className="analytics-view">
      <Crumbs parts={[{ label: "Analytics" }]} />
      <header className="page-head">
        <p className="kicker">Teacher · analytics</p>
        <h1>Class analytics</h1>
        <p>Everything about how your classes are doing, on one page.</p>
        {scopeDescription && (
          <p className="progress-label">Showing: {scopeDescription.toLowerCase()}</p>
        )}
      </header>

      {loading && <div className="banner banner--info">Loading your analytics…</div>}
      {classesError && (
        <div className="banner banner--warning" role="alert">
          {classesError}
        </div>
      )}

      {!loading && !classesError && classes.length === 0 && (
        <div className="banner banner--info" role="status">
          You have no teaching assignments in the current term, so there's nothing to show yet.
        </div>
      )}

      {!loading && !classesError && classes.length > 0 && (
        <>
          <div className="grid grid--2 analytics-kpi-grid">
            <div className="card is-locked">
              <p className="progress-label">Students</p>
              <h2>{totalStudents}</h2>
            </div>
            <div className="card is-locked">
              <p className="progress-label">Sections</p>
              <h2>{classes.length}</h2>
            </div>
            <div className="card is-locked">
              <p className="progress-label">Average mastery</p>
              <h2>{round(overallMastery)}</h2>
            </div>
            <div className="card is-locked">
              <p className="progress-label">Average attendance</p>
              <h2>{round(overallAttendance)}</h2>
            </div>
          </div>

          {totalAtRisk > 0 && (
            <div className="banner banner--info" role="status">
              {totalAtRisk} active at-risk flag{totalAtRisk === 1 ? "" : "s"} across your classes.{" "}
              <Link to="/teacher/at-risk">See at-risk flags →</Link>
            </div>
          )}

          <ClassHeatmap heatmap={heatmap} />

          <div className="analytics-sections">
            {sections.map((section) => (
              <SectionPanel key={section.sectionId} section={section} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

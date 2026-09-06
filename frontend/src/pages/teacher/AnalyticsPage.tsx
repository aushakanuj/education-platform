import { Link } from "react-router-dom";

import { Crumbs } from "../../components/Crumbs";
import { MasteryRing } from "../../components/MasteryRing";
import { useAtRiskFlags } from "../../lib/useAtRiskFlags";
import { useTeacherClasses } from "../../lib/useTeacherClasses";
import {
  computeSectionAnalytics,
  computeSubjectOverview,
  type SectionAnalytics,
} from "../../lib/teacherAnalytics";

function round(value: number | null): string {
  return value === null ? "—" : `${Math.round(value)}%`;
}

function progressTone(value: number): "progress--danger" | "progress--warn" | "progress--ok" {
  if (value >= 70) return "progress--ok";
  if (value >= 50) return "progress--warn";
  return "progress--danger";
}

function SubjectOverview({ subjects }: { subjects: { subject: string; averageMastery: number }[] }) {
  if (subjects.length === 0) return null;
  return (
    <section className="panel analytics-panel">
      <h2>Subjects that need attention</h2>
      <p className="progress-label">Averaged across every class you teach, weakest first.</p>
      <div className="analytics-subject-list">
        {subjects.map((entry) => (
          <div className="subject-bar-row" key={entry.subject}>
            <div className="subject-bar-row__head">
              <span>{entry.subject}</span>
              <span>{round(entry.averageMastery)}</span>
            </div>
            <div className={`progress ${progressTone(entry.averageMastery)}`}>
              <span style={{ width: `${Math.max(4, entry.averageMastery)}%` }} />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function DistributionBar({ distribution }: { distribution: SectionAnalytics["distribution"] }) {
  const total =
    distribution.strong + distribution.average + distribution.struggling + distribution.not_started;
  if (total === 0) return null;
  const seg = (count: number) => `${(count / total) * 100}%`;
  return (
    <div>
      <div className="distribution-bar" role="img" aria-label="Class performance distribution">
        {distribution.strong > 0 && (
          <span className="distribution-bar__seg distribution-bar__seg--strong" style={{ width: seg(distribution.strong) }} />
        )}
        {distribution.average > 0 && (
          <span className="distribution-bar__seg distribution-bar__seg--average" style={{ width: seg(distribution.average) }} />
        )}
        {distribution.struggling > 0 && (
          <span className="distribution-bar__seg distribution-bar__seg--struggling" style={{ width: seg(distribution.struggling) }} />
        )}
        {distribution.not_started > 0 && (
          <span className="distribution-bar__seg distribution-bar__seg--none" style={{ width: seg(distribution.not_started) }} />
        )}
      </div>
      <div className="distribution-bar__legend">
        <span className="chip"><i className="dot dot--strong" />{distribution.strong} strong</span>
        <span className="chip"><i className="dot dot--average" />{distribution.average} average</span>
        <span className="chip"><i className="dot dot--struggling" />{distribution.struggling} struggling</span>
        {distribution.not_started > 0 && (
          <span className="chip"><i className="dot dot--none" />{distribution.not_started} not started</span>
        )}
      </div>
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

      <DistributionBar distribution={section.distribution} />

      {section.subjectAverages.length > 0 && (
        <div className="analytics-subject-list analytics-subject-list--compact">
          {section.subjectAverages.map((entry) => (
            <div className="subject-bar-row" key={entry.subject}>
              <div className="subject-bar-row__head">
                <span>{entry.subject}</span>
                <span>{round(entry.averageMastery)}</span>
              </div>
              <div className={`progress ${progressTone(entry.averageMastery)}`}>
                <span style={{ width: `${Math.max(4, entry.averageMastery)}%` }} />
              </div>
            </div>
          ))}
        </div>
      )}

      {section.lowAttendance.length > 0 && (
        <div>
          <p className="progress-label">Below 75% attendance</p>
          <ul className="list">
            {section.lowAttendance.map((student) => (
              <li className="list-item" key={student.studentId}>
                <span className="list-item__num" aria-hidden="true">
                  !
                </span>
                <p className="list-item__title">{student.fullName}</p>
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
  const subjectOverview = computeSubjectOverview(classes);

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
    <>
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

          <SubjectOverview subjects={subjectOverview} />

          <div className="analytics-sections">
            {sections.map((section) => (
              <SectionPanel key={section.sectionId} section={section} />
            ))}
          </div>
        </>
      )}
    </>
  );
}

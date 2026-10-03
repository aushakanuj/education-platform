import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import type { AtRiskFlag } from "../../api/atRisk";
import { fetchDashboardSummary, type DashboardSummary } from "../../api/insights";
import { Crumbs } from "../../components/Crumbs";
import {
  countTooFewToCompare,
  curriculumCoverage,
  formatPercent,
  hasEnoughEvidence,
  isLowParticipation,
  MIN_SCORED_STUDENTS,
  passRate,
  plural,
  STRONG_MASTERY_PERCENT,
  summariseAtRisk,
  weakestSubjects,
} from "../../lib/adminDashboard";
import type { AdminGrade } from "../../lib/adminCurriculumLive";
import { useAdminDirectory } from "../../lib/useAdminDirectory";
import { useAtRiskFlags } from "../../lib/useAtRiskFlags";

import "./AdminDashboardPage.css";

type SummaryState = {
  loading: boolean;
  error: string | null;
  summary: DashboardSummary | null;
};

function useDashboardSummary(): SummaryState {
  const [state, setState] = useState<SummaryState>({ loading: true, error: null, summary: null });

  useEffect(() => {
    let cancelled = false;
    fetchDashboardSummary()
      .then((summary) => {
        if (!cancelled) setState({ loading: false, error: null, summary });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setState({
            loading: false,
            error: err instanceof Error ? err.message : "Could not load school numbers.",
            summary: null,
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}

/** Each section loads on its own, so one failing request never blanks the whole page. */
export function AdminDashboardPage() {
  const { loading: summaryLoading, error: summaryError, summary } = useDashboardSummary();
  const { loading: flagsLoading, error: flagsError, flags } = useAtRiskFlags();
  const { loading: directoryLoading, error: directoryError, grades } = useAdminDirectory();

  return (
    <div className="admin-dashboard">
      <Crumbs parts={[{ label: "Dashboard" }]} />
      <header className="page-head">
        <p className="kicker">Administrator · overview</p>
        <h1>Dashboard</h1>
        <p>What needs your attention, how the school is doing, and where the curriculum has gaps.</p>
      </header>

      <AttentionSection loading={flagsLoading} error={flagsError} flags={flags} />

      <section className="admin-dashboard__section" aria-labelledby="dash-glance">
        <h2 id="dash-glance" className="admin-dashboard__title">
          School at a glance
        </h2>
        {summaryLoading && <div className="banner banner--info">Loading school numbers…</div>}
        {summaryError && (
          <div className="banner banner--warning" role="alert">
            {summaryError}
          </div>
        )}
        {summary && (
          <div className="grid grid--2 analytics-kpi-grid">
            <div className="card is-locked">
              <p className="progress-label">Students</p>
              <h2>{summary.total_students}</h2>
            </div>
            <div className="card is-locked">
              <p className="progress-label">Average attendance</p>
              <h2>{formatPercent(summary.average_attendance)}</h2>
            </div>
            <div className="card is-locked">
              <p className="progress-label">Average mastery</p>
              <h2>{formatPercent(summary.average_mastery)}</h2>
              <p className="progress-label">Subjects with at least one quiz</p>
            </div>
          </div>
        )}
      </section>

      <section className="admin-dashboard__section" aria-labelledby="dash-look-into">
        <h2 id="dash-look-into" className="admin-dashboard__title">
          Subjects to look into
        </h2>
        {summaryLoading && <div className="banner banner--info">Loading subject results…</div>}
        {summary && <SubjectsToLookInto summary={summary} />}
      </section>

      <section className="admin-dashboard__section" aria-labelledby="dash-coverage">
        <h2 id="dash-coverage" className="admin-dashboard__title">
          Curriculum coverage
        </h2>
        {directoryLoading && <div className="banner banner--info">Loading curriculum…</div>}
        {directoryError && (
          <div className="banner banner--warning" role="alert">
            {directoryError}
          </div>
        )}
        {grades && <Coverage grades={grades} />}
      </section>
    </div>
  );
}

function AttentionSection({
  loading,
  error,
  flags,
}: {
  loading: boolean;
  error: string | null;
  flags: AtRiskFlag[];
}) {
  const counts = summariseAtRisk(flags);

  return (
    <section className="admin-dashboard__section" aria-labelledby="dash-attention">
      <h2 id="dash-attention" className="admin-dashboard__title">
        Needs your attention
      </h2>
      {loading && <div className="banner banner--info">Checking at-risk flags…</div>}
      {error && (
        <div className="banner banner--warning" role="alert">
          {error}
        </div>
      )}
      {!loading && !error && (
        <div className="panel admin-dashboard__attention">
          {counts.flags === 0 ? (
            <p className="admin-dashboard__lead">No students are flagged as at risk right now.</p>
          ) : (
            <>
              <p className="admin-dashboard__lead">
                <strong>{plural(counts.students, "student")}</strong> flagged as at risk (
                {plural(counts.flags, "active flag")})
              </p>
              <div className="meta-row">
                {counts.urgent > 0 && (
                  <span className="badge badge--warn">{counts.urgent} urgent</span>
                )}
                {counts.attention > 0 && (
                  <span className="badge badge--info">{counts.attention} attention</span>
                )}
                {counts.monitor > 0 && <span className="badge">{counts.monitor} monitor</span>}
              </div>
            </>
          )}
          <Link to="/admin/at-risk" className="admin-dashboard__link">
            {counts.flags === 0 ? "Open at-risk flags →" : "Review at-risk flags →"}
          </Link>
        </div>
      )}
    </section>
  );
}

function SubjectsToLookInto({ summary }: { summary: DashboardSummary }) {
  const weakest = weakestSubjects(summary.subjects);
  const tooFew = countTooFewToCompare(summary.subjects);
  const tooFewNote =
    tooFew > 0
      ? `${plural(tooFew, "subject")} not shown yet: fewer than ${MIN_SCORED_STUDENTS} students have taken a quiz.`
      : null;

  if (weakest.length === 0) {
    const anyComparable = summary.subjects.some(hasEnoughEvidence);
    return (
      <>
        <div className="banner banner--info" role="status">
          {anyComparable
            ? `Every subject with enough quiz results is averaging ${STRONG_MASTERY_PERCENT}% or above.`
            : `No subject has quiz results from at least ${MIN_SCORED_STUDENTS} students yet, so there is nothing to compare.`}
        </div>
        {tooFewNote && <p className="progress-label">{tooFewNote}</p>}
      </>
    );
  }

  return (
    <div className="panel">
      <p className="progress-label">
        Subjects averaging below {STRONG_MASTERY_PERCENT}% quiz mastery, lowest first. This shows
        where students are struggling, not why: the topic's difficulty, the quiz questions,
        attendance, and how many students took part all play a role.
      </p>
      <ol className="admin-dashboard__weakest">
        {weakest.map((subject) => {
          const mastery = subject.average_mastery ?? 0;
          const rate = passRate(subject);
          const tone =
            mastery < 50 ? "progress--danger" : mastery < 70 ? "progress--warn" : "progress--ok";
          return (
            <li key={`${subject.grade}-${subject.subject}`}>
              <div className="subject-bar-row__head">
                <span>
                  {subject.grade} · {subject.subject}
                </span>
                <span>{formatPercent(subject.average_mastery)}</span>
              </div>
              <div className={`progress ${tone}`} aria-hidden="true">
                <span style={{ width: `${Math.min(100, Math.max(0, mastery))}%` }} />
              </div>
              <div className="meta-row">
                <span className="progress-label">
                  {subject.students_attempted} of {plural(subject.students, "student")} attempted a
                  quiz
                  {rate !== null && ` · ${Math.round(rate)}% of attempts passed`}
                </span>
                {isLowParticipation(subject) && (
                  <span
                    className="badge badge--info"
                    title="Fewer than 80% of students have taken a quiz, so this average may change."
                  >
                    Low participation
                  </span>
                )}
              </div>
            </li>
          );
        })}
      </ol>
      {tooFewNote && <p className="progress-label admin-dashboard__footnote">{tooFewNote}</p>}
    </div>
  );
}

function Coverage({ grades }: { grades: AdminGrade[] }) {
  const coverage = curriculumCoverage(grades);

  if (coverage.grades.length === 0) {
    return (
      <div className="banner banner--info" role="status">
        No grades in the curriculum yet.
      </div>
    );
  }

  return (
    <>
      <p className="progress-label">
        {coverage.subjectsWithContent} of {plural(coverage.totalSubjects, "subject")} have published
        topics · {plural(coverage.totalTopics, "topic")} in total
      </p>
      <div className="admin-dashboard__coverage">
        {coverage.grades.map((grade) => (
          <div className="panel" key={grade.key}>
            <div className="meta-row admin-dashboard__grade-head">
              <h3>{grade.name}</h3>
              {grade.emptySubjects > 0 && (
                <span className="badge badge--warn">
                  {grade.emptySubjects} without content
                </span>
              )}
            </div>
            <ul className="admin-dashboard__subjects">
              {grade.subjects.map((subject) => (
                <li key={subject.id}>
                  <Link to={`/admin/materials/grades/${grade.key}/subjects/${subject.id}`}>
                    {subject.name}
                  </Link>
                  {subject.topics === 0 ? (
                    <span className="badge badge--warn">No content yet</span>
                  ) : (
                    <span className="progress-label">
                      {plural(subject.topics, "topic")} · {plural(subject.quizzes, "quiz", "quizzes")}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </>
  );
}

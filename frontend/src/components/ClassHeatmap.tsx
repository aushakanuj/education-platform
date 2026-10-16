import { Link } from "react-router-dom";

import { cellTintPercent, tierFor, type Heatmap, type PerformanceTier } from "../lib/teacherAnalytics";

const HUE: Record<PerformanceTier, string> = {
  strong: "var(--success)",
  average: "var(--warning)",
  struggling: "var(--danger)",
  not_started: "var(--border)",
};

function tint(mastery: number | null): { background: string } | undefined {
  if (mastery === null) return undefined;
  return {
    background: `color-mix(in srgb, ${HUE[tierFor(mastery)]} ${cellTintPercent(mastery)}%, transparent)`,
  };
}

function label(mastery: number | null): string {
  return mastery === null ? "—" : `${Math.round(mastery)}`;
}

/**
 * Every class against every subject, in one grid.
 *
 * Reading down the last column compares classes; reading along the bottom row finds the
 * subject that is weak everywhere; a cell finds the one class-and-subject pair that needs a
 * lesson replanned. Colour carries the magnitude so the eye lands on the problem before it
 * reads a single number.
 */
export function ClassHeatmap({ heatmap }: { heatmap: Heatmap }) {
  if (heatmap.rows.length === 0 || heatmap.subjects.length === 0) return null;

  return (
    <section className="panel analytics-panel">
      <h2>Where to look first</h2>
      <p className="progress-label">
        Average mastery per class and subject. Deeper colour means further from where you'd
        want it — red below, green above. Click a class to open its roster.
      </p>
      <div className="heatmap-scroll">
        <table className="heatmap">
          <thead>
            <tr>
              <th scope="col">Class</th>
              {heatmap.subjects.map((subject) => (
                <th scope="col" key={subject}>
                  {subject}
                </th>
              ))}
              <th scope="col" className="heatmap__overall-head">
                Overall
              </th>
            </tr>
          </thead>
          <tbody>
            {heatmap.rows.map((row) => (
              <tr key={row.key} className={row.kind === "section" ? "" : "heatmap__row--summary"}>
                <th scope="row">
                  {row.sectionId ? (
                    <Link className="heatmap__class" to={`/teacher/classes/${row.sectionId}/students`}>
                      {row.label}
                    </Link>
                  ) : (
                    <span className="heatmap__class">{row.label}</span>
                  )}
                  <span className="heatmap__count">
                    {row.studentCount} student{row.studentCount === 1 ? "" : "s"}
                  </span>
                </th>
                {row.cells.map((value, index) => (
                  <td key={heatmap.subjects[index]} style={tint(value)}>
                    {label(value)}
                  </td>
                ))}
                <td style={tint(row.overall)} className="heatmap__overall">
                  {label(row.overall)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

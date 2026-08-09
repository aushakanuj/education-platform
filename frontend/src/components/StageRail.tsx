import { NavLink } from "react-router-dom";

export type Stage = {
  id: string;
  num: string;
  label: string;
  to: string;
  done?: boolean;
};

type StageRailProps = {
  stages: Stage[];
  horizontal?: boolean;
};

export function StageRail({ stages, horizontal = false }: StageRailProps) {
  return (
    <ul
      className={`stage-rail ${horizontal ? "stage-rail--horizontal" : ""}`}
      aria-label="Study stages"
    >
      {stages.map((stage) => (
        <li key={stage.id}>
          <NavLink
            to={stage.to}
            className={({ isActive }) =>
              [
                "stage-rail__item",
                isActive ? "is-active" : "",
                stage.done ? "is-done" : "",
              ]
                .filter(Boolean)
                .join(" ")
            }
            end={stage.to === "/"}
          >
            <span className="stage-rail__num">{stage.num}</span>
            <span className="stage-rail__label">{stage.label}</span>
          </NavLink>
        </li>
      ))}
    </ul>
  );
}

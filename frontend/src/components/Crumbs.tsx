import { Link } from "react-router-dom";

export type Crumb = {
  label: string;
  to?: string;
};

export function Crumbs({ parts }: { parts: Crumb[] }) {
  return (
    <nav className="crumbs" aria-label="Breadcrumb">
      {parts.map((part, index) => {
        const isLast = index === parts.length - 1;
        return (
          <span key={`${part.label}-${index}`} className="crumbs__item">
            {part.to && !isLast ? (
              <Link to={part.to}>{part.label}</Link>
            ) : (
              <span aria-current={isLast ? "page" : undefined}>{part.label}</span>
            )}
            {!isLast && <span className="crumbs__sep">/</span>}
          </span>
        );
      })}
    </nav>
  );
}

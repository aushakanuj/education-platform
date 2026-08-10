import { Link } from "react-router-dom";

import { Crumbs } from "../../components/Crumbs";

/** Optional nav stub — policy/RAG assistant is out of scope for this mock. */
export function AssistantStubPage() {
  return (
    <>
      <Crumbs
        parts={[
          { label: "My classes", to: "/teacher" },
          { label: "Assistant" },
        ]}
      />
      <div className="back-row">
        <Link to="/teacher" className="btn btn--outline btn--sm">
          ← Back to my classes
        </Link>
      </div>
      <header className="page-head">
        <p className="kicker">Teacher · coming later</p>
        <h1>Assistant</h1>
        <p>
          A teaching assistant chat is planned for a later phase. This page is a navigation stub
          only.
        </p>
      </header>
      <div className="banner banner--info" role="status">
        Fixture workspace · no retrieval or policy chat wired for teachers yet.
      </div>
    </>
  );
}

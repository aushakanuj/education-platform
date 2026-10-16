import { useParams } from "react-router-dom";

import { Crumbs } from "../../components/Crumbs";
import { TopicGenerationUpload } from "../../components/TopicGenerationUpload";

export function GenerationRunsPage() {
  const { topicId = "" } = useParams();

  return (
    <div className="admin-materials">
      <Crumbs parts={[{ label: "My classes", to: "/teacher" }, { label: "Generation review" }]} />
      <header className="page-head">
        <p className="kicker">Teacher · shared curriculum</p>
        <h1>Topic generation review</h1>
        <p>
          Teachers approve or request changes on a frozen outline. They do not edit the shared
          curriculum or upload PDFs. An administrator closes the round.
        </p>
      </header>
      {topicId ? (
        <TopicGenerationUpload topicId={topicId} allowUpload={false} />
      ) : (
        <p className="muted">No topic selected.</p>
      )}
    </div>
  );
}

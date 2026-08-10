import { Navigate, useParams } from "react-router-dom";

/** Legacy topic URLs forward to the subject material hub. */
export function TopicPageRedirect() {
  const { subjectId = "", topicId: _topicId, subtopicId } = useParams();

  if (subtopicId) {
    return (
      <Navigate to={`/subjects/${subjectId}/subtopics/${subtopicId}/lesson`} replace />
    );
  }

  return <Navigate to={`/subjects/${subjectId}`} replace />;
}

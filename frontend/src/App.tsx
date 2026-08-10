import { Navigate, Route, Routes } from "react-router-dom";

import { RequireAuth } from "./auth/RequireAuth";
import { RequireEnrollment } from "./auth/RequireEnrollment";
import { EnrollPage } from "./pages/EnrollPage";
import { HomePage } from "./pages/HomePage";
import { LessonPage } from "./pages/LessonPage";
import { QuizPage } from "./pages/QuizPage";
import { ResultPage } from "./pages/ResultPage";
import { TopicPageRedirect } from "./pages/TopicPageRedirect";
import { WelcomePage } from "./pages/WelcomePage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<WelcomePage />} />
      <Route
        path="/enroll"
        element={
          <RequireAuth>
            <EnrollPage />
          </RequireAuth>
        }
      />
      <Route
        path="/"
        element={
          <RequireAuth>
            <RequireEnrollment>
              <HomePage />
            </RequireEnrollment>
          </RequireAuth>
        }
      />
      <Route
        path="/subjects/:subjectId"
        element={
          <RequireAuth>
            <RequireEnrollment>
              <HomePage />
            </RequireEnrollment>
          </RequireAuth>
        }
      />
      <Route
        path="/subjects/:subjectId/topics/:topicId"
        element={
          <RequireAuth>
            <RequireEnrollment>
              <TopicPageRedirect />
            </RequireEnrollment>
          </RequireAuth>
        }
      />
      <Route
        path="/subjects/:subjectId/subtopics/:subtopicId/lesson"
        element={
          <RequireAuth>
            <RequireEnrollment>
              <LessonPage />
            </RequireEnrollment>
          </RequireAuth>
        }
      />
      <Route
        path="/subjects/:subjectId/topics/:topicId/subtopics/:subtopicId/lesson"
        element={
          <RequireAuth>
            <RequireEnrollment>
              <TopicPageRedirect />
            </RequireEnrollment>
          </RequireAuth>
        }
      />
      <Route
        path="/quizzes/:quizId"
        element={
          <RequireAuth>
            <RequireEnrollment>
              <QuizPage />
            </RequireEnrollment>
          </RequireAuth>
        }
      />
      <Route
        path="/attempts/:attemptId"
        element={
          <RequireAuth>
            <RequireEnrollment>
              <ResultPage />
            </RequireEnrollment>
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

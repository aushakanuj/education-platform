import { Navigate, Route, Routes } from "react-router-dom";

import { RequireAuth } from "./auth/RequireAuth";
import { RequireEnrollment } from "./auth/RequireEnrollment";
import { RequireRole } from "./auth/RequireRole";
import { ROLE_ADMIN, ROLE_TEACHER } from "./auth/roles";
import { AdminShell } from "./components/AdminShell";
import { TeacherShell } from "./components/TeacherShell";
import { EnrollPage } from "./pages/EnrollPage";
import { HomePage } from "./pages/HomePage";
import { LessonPage } from "./pages/LessonPage";
import { LessonSlidesPage } from "./pages/LessonSlidesPage";
import { QuizHistoryPage } from "./pages/QuizHistoryPage";
import { QuizPage } from "./pages/QuizPage";
import { ResultPage } from "./pages/ResultPage";
import { TopicPageRedirect } from "./pages/TopicPageRedirect";
import { WelcomePage } from "./pages/WelcomePage";
import { AdminDocumentsPage } from "./pages/admin/AdminDocumentsPage";
import { AdminMaterialsGradesPage } from "./pages/admin/AdminMaterialsGradesPage";
import { AdminMaterialsSubjectsPage } from "./pages/admin/AdminMaterialsSubjectsPage";
import { AdminMaterialsTopicDetailPage } from "./pages/admin/AdminMaterialsTopicDetailPage";
import { AdminMaterialsTopicsPage } from "./pages/admin/AdminMaterialsTopicsPage";
import { PolicyChatPage } from "./pages/admin/PolicyChatPage";
import { AssistantStubPage } from "./pages/teacher/AssistantStubPage";
import { ClassesPage } from "./pages/teacher/ClassesPage";
import { RosterPage } from "./pages/teacher/RosterPage";
import { SectionPage } from "./pages/teacher/SectionPage";
import { SubjectMaterialsPage } from "./pages/teacher/SubjectMaterialsPage";

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
        path="/admin"
        element={
          <RequireAuth>
            <RequireRole roles={ROLE_ADMIN}>
              <AdminShell />
            </RequireRole>
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="materials" replace />} />
        <Route path="materials" element={<AdminMaterialsGradesPage />} />
        <Route path="materials/grades/:gradeKey" element={<AdminMaterialsSubjectsPage />} />
        <Route
          path="materials/grades/:gradeKey/subjects/:subjectId"
          element={<AdminMaterialsTopicsPage />}
        />
        <Route
          path="materials/grades/:gradeKey/subjects/:subjectId/topics/:topicId"
          element={<AdminMaterialsTopicDetailPage />}
        />
        <Route path="documents" element={<AdminDocumentsPage />} />
        <Route path="policy" element={<PolicyChatPage />} />
      </Route>

      <Route
        path="/teacher"
        element={
          <RequireAuth>
            <RequireRole roles={ROLE_TEACHER}>
              <TeacherShell />
            </RequireRole>
          </RequireAuth>
        }
      >
        <Route index element={<ClassesPage />} />
        <Route path="assistant" element={<AssistantStubPage />} />
        <Route path="classes/:sectionId" element={<SectionPage />} />
        <Route path="classes/:sectionId/students" element={<RosterPage />} />
        <Route
          path="classes/:sectionId/subjects/:subjectId"
          element={<SubjectMaterialsPage />}
        />
      </Route>

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
        path="/subjects/:subjectId/subtopics/:subtopicId/lesson/slides"
        element={
          <RequireAuth>
            <RequireEnrollment>
              <LessonSlidesPage />
            </RequireEnrollment>
          </RequireAuth>
        }
      />
      <Route
        path="/subjects/:subjectId/subtopics/:subtopicId/lesson/history"
        element={
          <RequireAuth>
            <RequireEnrollment>
              <QuizHistoryPage />
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

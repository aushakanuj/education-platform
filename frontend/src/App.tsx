import { Navigate, Route, Routes } from "react-router-dom";

import { RequireAuth } from "./auth/RequireAuth";
import { RequireEnrollment } from "./auth/RequireEnrollment";
import { RequireRole } from "./auth/RequireRole";
import { ROLE_ADMIN, ROLE_TEACHER } from "./auth/roles";
import { AdminShell } from "./components/AdminShell";
import { AppShell } from "./components/AppShell";
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
import { QuestionBankPage } from "./pages/teacher/QuestionBankPage";
import { ClassesPage } from "./pages/teacher/ClassesPage";
import { RosterPage } from "./pages/teacher/RosterPage";
import { SectionPage } from "./pages/teacher/SectionPage";
import { StudentPage } from "./pages/teacher/StudentPage";
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
        <Route path="questions" element={<QuestionBankPage />} />
        <Route path="classes/:sectionId" element={<SectionPage />} />
        <Route path="classes/:sectionId/students" element={<RosterPage />} />
        <Route path="classes/:sectionId/students/:studentId" element={<StudentPage />} />
        <Route
          path="classes/:sectionId/subjects/:subjectId"
          element={<SubjectMaterialsPage />}
        />
      </Route>

      <Route
        element={
          <RequireAuth>
            <RequireEnrollment>
              <AppShell />
            </RequireEnrollment>
          </RequireAuth>
        }
      >
        <Route index element={<HomePage />} />
        <Route path="subjects/:subjectId" element={<HomePage />} />
        <Route path="subjects/:subjectId/topics/:topicId" element={<TopicPageRedirect />} />
        <Route
          path="subjects/:subjectId/subtopics/:subtopicId/lesson/slides"
          element={<LessonSlidesPage />}
        />
        <Route
          path="subjects/:subjectId/subtopics/:subtopicId/lesson/history"
          element={<QuizHistoryPage />}
        />
        <Route path="subjects/:subjectId/subtopics/:subtopicId/lesson" element={<LessonPage />} />
        <Route
          path="subjects/:subjectId/topics/:topicId/subtopics/:subtopicId/lesson"
          element={<TopicPageRedirect />}
        />
        <Route path="quizzes/:quizId" element={<QuizPage />} />
        <Route path="attempts/:attemptId" element={<ResultPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

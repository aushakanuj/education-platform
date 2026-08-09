/** Shared API types mirroring backend Pydantic schemas. */

export type TokenResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
};

export type MeResponse = {
  id: string;
  email: string;
  full_name: string;
  institution_id: string;
  roles: string[];
  student_profile_id: string | null;
  status: string;
};

export type ProvisionStudentRequest = {
  email: string;
  password: string;
  full_name: string;
  student_identifier: string;
  institution_name?: string;
};

export type LoginRequest = {
  email: string;
  password: string;
  institution_name?: string;
};

export type GradeEnrollment = {
  id: string;
  academic_period_id: string;
  academic_period_name: string;
  academic_period_status: string;
  grade_id: string;
  grade_name: string;
  status: string;
};

export type SubjectEnrollment = {
  id: string;
  grade_subject_offering_id: string;
  academic_period_id: string;
  academic_period_name: string;
  grade_name: string;
  subject_id: string;
  subject_code: string;
  subject_name: string;
  status: string;
};

export type EnrollmentSummary = {
  grade_enrollments: GradeEnrollment[];
  subject_enrollments: SubjectEnrollment[];
  eligible?: boolean;
  blocked_reason?: string | null;
};

export type DemoBootstrapResponse = {
  subject_id: string;
  topic_id: string;
  topic_title: string;
  message: string;
};

export type AttemptHistoryItem = {
  id: string;
  attempt_number: number;
  status: string;
  score_percent: string | number | null;
  passed: boolean | null;
  started_at: string | null;
  submitted_at: string | null;
};

export type QuizSummary = {
  id: string;
  title: string;
  scope: "subtopic_mastery" | "topic_mastery";
  available: boolean;
  unlocked: boolean;
  locked_reason: string | null;
  pass_threshold_percent: number;
  attempt_count: number;
  best_score_percent: number | null;
  passed: boolean;
  in_progress_attempt_id: string | null;
  recent_attempts: AttemptHistoryItem[];
};

export type MaterialProgress = {
  status: "opened" | "completed";
  opened_at: string;
  last_opened_at: string;
  completed_at: string | null;
  last_unit_ordinal: number | null;
  source_material_version_id: string;
};

export type SubtopicNode = {
  id: string;
  title: string;
  slug: string;
  sequence: number;
  has_lesson: boolean;
  lesson_completed: boolean;
  progress_percent: number;
  progress?: MaterialProgress | null;
  source_material_version_id?: string | null;
  quiz: QuizSummary | null;
};

export type TopicNode = {
  id: string;
  title: string;
  slug: string;
  sequence: number;
  progress_percent: number;
  complete: boolean;
  objectives: string[];
  subtopics: SubtopicNode[];
  overall_quiz: QuizSummary | null;
};

export type SubjectNode = {
  id: string;
  code: string;
  name: string;
  grade_name: string;
  academic_period_name: string;
  progress_percent: number;
  topics: TopicNode[];
};

export type LearningDirectory = {
  subjects: SubjectNode[];
};

export type LessonSlide = {
  number: number;
  title: string;
  content: string;
};

export type LessonMaterial = {
  id: string;
  title: string;
  markdown: string;
  slides: LessonSlide[];
  source_material_version_id: string;
  progress: MaterialProgress | null;
  quiz_unlocked: boolean;
  quiz_id: string | null;
};

export type MaterialProgressUpdate = {
  status: "opened" | "completed";
  last_unit_ordinal?: number | null;
};

export type QuizOption = {
  label: string;
  text: string;
};

export type QuizQuestion = {
  number: number;
  difficulty: string | null;
  prompt: string;
  options: QuizOption[];
};

export type QuizMaterial = {
  id: string;
  title: string;
  questions: QuizQuestion[];
  pass_threshold_percent: number;
  duration_seconds: number | null;
  max_attempts: number | null;
  result_release_mode: string;
};

export type StartAttemptResponse = {
  id: string;
  quiz_id: string;
  quiz_version_id: string;
  attempt_number: number;
  status: string;
  started_at: string | null;
  deadline_at: string | null;
  pass_threshold_percent: number;
  result_release_mode: string;
  title: string;
  scope: "subtopic_mastery" | "topic_mastery";
  target_id: string;
  questions: QuizQuestion[];
};

export type AnswerSubmission = {
  question_number: number;
  selected_option_label: string;
};

export type SubmitAttemptRequest = {
  answers: AnswerSubmission[];
};

export type AttemptAnswerOut = {
  question_number: number;
  selected_option_label: string | null;
  is_correct: boolean | null;
  marks_awarded: string | number | null;
};

export type AttemptResult = {
  id: string;
  quiz_id: string;
  target_id: string | null;
  scope: "subtopic_mastery" | "topic_mastery" | null;
  attempt_number: number;
  status: string;
  started_at: string | null;
  submitted_at: string | null;
  scored_at: string | null;
  score_raw: string | number | null;
  score_percent: string | number | null;
  pass_threshold_percent: number | null;
  passed: boolean | null;
  review_available: boolean;
  answers: AttemptAnswerOut[];
};

/** @deprecated flat catalog shape retained for transitional callers */
export type TopicSummary = {
  id: string;
  title: string;
  has_lesson: boolean;
  has_quiz: boolean;
};

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

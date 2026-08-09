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
};

export type TopicSummary = {
  id: string;
  title: string;
  has_lesson: boolean;
  has_quiz: boolean;
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
};

export type StartAttemptResponse = {
  id: string;
  topic_id: string;
  quiz_version_id: string;
  attempt_number: number;
  status: string;
  started_at: string | null;
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
  topic_id: string;
  attempt_number: number;
  status: string;
  started_at: string | null;
  submitted_at: string | null;
  scored_at: string | null;
  score_raw: string | number | null;
  score_percent: string | number | null;
  passed: boolean | null;
  answers: AttemptAnswerOut[];
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

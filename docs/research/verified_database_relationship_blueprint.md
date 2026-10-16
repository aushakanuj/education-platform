# Verified Database Relationship Blueprint

**Verification source:** live PostgreSQL database `education`, schema `public`, verified 2026-09-05.

This report is an analysis blueprint only. It does not modify the database, existing schema catalogue, prompt, or application code.

## 1. Database Overview

- 44 public relations reported: 42 application tables, `student_360` view, and `alembic_version`.
- 68 direct foreign-key constraints.
- No composite foreign keys.
- No native PostgreSQL enum types. Status and lifecycle fields are generally `VARCHAR`.
- `chunk_embeddings.embedding` uses the PostgreSQL `vector` type.
- `student_360` is a denormalized analytical view without a primary key.

## 2. Tables and Primary Keys

All application tables use a UUID `id` primary key unless noted. `?` means nullable.

### Identity and tenancy

- `institutions`: `id`, `created_at`, `updated_at`, `name`, `timezone`, `status`
- `users`: `id`, `created_at`, `updated_at`, `institution_id`, `email`, `full_name`, `password_hash`, `status`
- `user_roles`: `id`, `created_at`, `updated_at`, `user_id`, `role`
- `student_profiles`: `id`, `created_at`, `updated_at`, `institution_id`, `user_id?`, `student_identifier`, `full_name`, `status`
- `refresh_sessions`: `id`, `created_at`, `updated_at`, `user_id`, `token_hash`, `expires_at`, `revoked_at?`
- `audit_events`: `id`, `institution_id`, `actor_user_id?`, `event_type`, `entity_type`, `entity_id?`, `payload`, `created_at`

### Academic structure

- `academic_periods`: `id`, `created_at`, `updated_at`, `institution_id`, `name`, `start_date`, `end_date`, `status`
- `grades`: `id`, `created_at`, `updated_at`, `institution_id`, `name`, `sort_order`
- `period_grades`: `id`, `created_at`, `updated_at`, `academic_period_id`, `grade_id`
- `sections`: `id`, `created_at`, `updated_at`, `period_grade_id`, `name`
- `subjects`: `id`, `created_at`, `updated_at`, `institution_id`, `name`, `code`
- `grade_subject_offerings`: `id`, `created_at`, `updated_at`, `period_grade_id`, `subject_id`
- `topics`: `id`, `created_at`, `updated_at`, `grade_subject_offering_id`, `name`, `slug`, `sequence`
- `subtopics`: `id`, `created_at`, `updated_at`, `topic_id`, `name`, `slug`, `sequence`
- `teaching_assignments`: `id`, `created_at`, `updated_at`, `teacher_user_id`, `academic_period_id`, `grade_subject_offering_id`, `section_id?`
- `student_grade_enrollments`: `id`, `created_at`, `updated_at`, `student_id`, `academic_period_id`, `period_grade_id`, `section_id?`, `status`
- `student_subject_enrollments`: `id`, `created_at`, `updated_at`, `student_id`, `grade_enrollment_id`, `grade_subject_offering_id`, `status`

### Assessments and quizzes

- `common_mastery_quizzes`: `id`, `created_at`, `updated_at`, `quiz_scope`, `subtopic_id?`, `topic_id?`, `title`
- `quiz_versions`: `id`, `created_at`, `updated_at`, `quiz_id`, `version_number`, `lifecycle_status`, `duration_seconds?`, `max_attempts?`, `result_release_mode`, `released_at?`, `pass_threshold_percent`
- `quiz_releases`: `id`, `created_at`, `updated_at`, `quiz_version_id`, `window_starts_at?`, `window_ends_at?`, `released_by_user_id?`, `status`
- `quiz_attempts`: `id`, `created_at`, `updated_at`, `student_id`, `quiz_version_id`, `attempt_number`, `status`, `started_at?`, `submitted_at?`, `scored_at?`, `score_raw?`, `score_percent?`, `passed?`, `student_subject_enrollment_id?`, `quiz_release_id?`, `deadline_at?`, `pass_threshold_percent?`
- `questions`: `id`, `created_at`, `updated_at`, `subtopic_id`, `code?`
- `question_versions`: `id`, `created_at`, `updated_at`, `question_id`, `version_number`, `prompt`, `question_type`, `difficulty?`, `marks`, `explanation?`, `lifecycle_status`
- `quiz_items`: `id`, `created_at`, `updated_at`, `quiz_version_id`, `question_version_id`, `sequence`
- `question_options`: `id`, `created_at`, `updated_at`, `question_version_id`, `label`, `text`, `sequence`
- `question_answer_keys`: `id`, `created_at`, `updated_at`, `question_version_id`, `correct_option_label?`, `correct_boolean?`, `correct_numeric?`, `correct_mapping?`, `scoring_rubric`
- `attempt_answers`: `id`, `created_at`, `updated_at`, `attempt_id`, `question_version_id`, `selected_option_label?`, `selected_boolean?`, `selected_numeric?`, `selected_mapping?`, `is_correct?`, `marks_awarded?`
- `quiz_material_bindings`: `id`, `created_at`, `updated_at`, `quiz_version_id`, `source_material_version_id`
- `learning_outcomes`: `id`, `created_at`, `updated_at`, `subtopic_id`, `code`, `statement`, `sequence`
- `question_outcome_tags`: `id`, `created_at`, `updated_at`, `question_version_id`, `learning_outcome_id`

### Materials and knowledge

- `source_materials`: `id`, `created_at`, `updated_at`, `subtopic_id`, `title`, `slug`, `status`
- `source_material_versions`: `id`, `created_at`, `updated_at`, `source_material_id`, `version_number`, `lifecycle_status`, `title`, `content_markdown?`, `content_format`, `blob_object_key?`, `blob_content_type?`, `checksum?`, `failure_reason?`, `published_at?`
- `source_chunks`: `id`, `created_at`, `updated_at`, `source_material_version_id`, `ordinal`, `text`, `content_hash`, `page_number?`, `section_heading?`, `token_count?`
- `knowledge_documents`: `id`, `created_at`, `updated_at`, `institution_id`, `title`, `slug`, `doc_type`, `status`, `required_roles`
- `knowledge_document_versions`: `id`, `created_at`, `updated_at`, `document_id`, `version_number`, `lifecycle_status`, `blob_object_key?`, `blob_content_type?`, `checksum?`, `failure_reason?`, `published_at?`
- `knowledge_chunks`: `id`, `created_at`, `updated_at`, `knowledge_document_version_id`, `ordinal`, `text`, `content_hash`, `page_number?`, `section_heading?`, `token_count?`
- `chunk_embeddings`: `chunk_id`, `embedding`, `doc_id`, `doc_kind`, `institution_id`, `required_roles`, `doc_type?`, `page_number?`, `version_id`
- `ingest_jobs`: `id`, `created_at`, `updated_at`, `status`, `error?`, `source_material_version_id?`, `knowledge_document_version_id?`

### Attendance, progress, chat, and derived relations

- `attendance_records`: `id`, `created_at`, `updated_at`, `student_id`, `academic_period_id`, `section_id?`, `grade_subject_offering_id?`, `on_date`, `status`, `recorded_by_user_id?`, `note?`
- `student_material_progress`: `id`, `created_at`, `updated_at`, `student_subject_enrollment_id`, `source_material_version_id`, `status`, `opened_at`, `last_opened_at`, `completed_at?`, `last_unit_ordinal?`
- `chat_conversations`: `id`, `created_at`, `updated_at`, `institution_id`, `owner_user_id`, `title`, `context_used_tokens`, `context_limit_tokens`, `context_used_percent`
- `chat_messages`: `id`, `created_at`, `updated_at`, `conversation_id`, `role`, `content`, `citations?`, `token_estimate`
- `student_360`: view with denormalized student, enrollment, subject, quiz, mastery, progress, and attendance fields
- `alembic_version`: `version_num`, migration metadata

## 3. Complete Foreign-Key Map

All relationships below are verified direct PostgreSQL foreign keys. Every edge is child-to-parent. Child columns marked `NULLABLE` accept nulls. No composite FK exists.

```text
academic_periods.institution_id → institutions.id
grades.institution_id → institutions.id
subjects.institution_id → institutions.id
users.institution_id → institutions.id
student_profiles.institution_id → institutions.id
audit_events.institution_id → institutions.id
knowledge_documents.institution_id → institutions.id
chat_conversations.institution_id → institutions.id

user_roles.user_id → users.id
refresh_sessions.user_id → users.id
student_profiles.user_id [NULLABLE] → users.id
audit_events.actor_user_id [NULLABLE] → users.id
teaching_assignments.teacher_user_id → users.id
quiz_releases.released_by_user_id [NULLABLE] → users.id
attendance_records.recorded_by_user_id [NULLABLE] → users.id
chat_conversations.owner_user_id → users.id

period_grades.academic_period_id → academic_periods.id
period_grades.grade_id → grades.id
sections.period_grade_id → period_grades.id
grade_subject_offerings.period_grade_id → period_grades.id
grade_subject_offerings.subject_id → subjects.id
topics.grade_subject_offering_id → grade_subject_offerings.id
subtopics.topic_id → topics.id
teaching_assignments.academic_period_id → academic_periods.id
teaching_assignments.grade_subject_offering_id → grade_subject_offerings.id
teaching_assignments.section_id [NULLABLE] → sections.id
student_grade_enrollments.student_id → student_profiles.id
student_grade_enrollments.academic_period_id → academic_periods.id
student_grade_enrollments.period_grade_id → period_grades.id
student_grade_enrollments.section_id [NULLABLE] → sections.id
student_subject_enrollments.student_id → student_profiles.id
student_subject_enrollments.grade_enrollment_id → student_grade_enrollments.id
student_subject_enrollments.grade_subject_offering_id → grade_subject_offerings.id

common_mastery_quizzes.subtopic_id [NULLABLE] → subtopics.id
common_mastery_quizzes.topic_id [NULLABLE] → topics.id
quiz_versions.quiz_id → common_mastery_quizzes.id
quiz_releases.quiz_version_id → quiz_versions.id
quiz_attempts.student_id → student_profiles.id
quiz_attempts.quiz_version_id → quiz_versions.id
quiz_attempts.quiz_release_id [NULLABLE] → quiz_releases.id
quiz_attempts.student_subject_enrollment_id [NULLABLE] → student_subject_enrollments.id
questions.subtopic_id → subtopics.id
question_versions.question_id → questions.id
quiz_items.quiz_version_id → quiz_versions.id
quiz_items.question_version_id → question_versions.id
question_options.question_version_id → question_versions.id
question_answer_keys.question_version_id → question_versions.id
attempt_answers.attempt_id → quiz_attempts.id
attempt_answers.question_version_id → question_versions.id
learning_outcomes.subtopic_id → subtopics.id
question_outcome_tags.question_version_id → question_versions.id
question_outcome_tags.learning_outcome_id → learning_outcomes.id
quiz_material_bindings.quiz_version_id → quiz_versions.id
quiz_material_bindings.source_material_version_id → source_material_versions.id

source_materials.subtopic_id → subtopics.id
source_material_versions.source_material_id → source_materials.id
source_chunks.source_material_version_id → source_material_versions.id
knowledge_document_versions.document_id → knowledge_documents.id
knowledge_chunks.knowledge_document_version_id → knowledge_document_versions.id
ingest_jobs.source_material_version_id [NULLABLE] → source_material_versions.id
ingest_jobs.knowledge_document_version_id [NULLABLE] → knowledge_document_versions.id

attendance_records.student_id → student_profiles.id
attendance_records.academic_period_id → academic_periods.id
attendance_records.section_id [NULLABLE] → sections.id
attendance_records.grade_subject_offering_id [NULLABLE] → grade_subject_offerings.id
student_material_progress.student_subject_enrollment_id → student_subject_enrollments.id
student_material_progress.source_material_version_id → source_material_versions.id
chat_messages.conversation_id → chat_conversations.id
```

Non-FK references:

```text
audit_events.entity_id
chunk_embeddings.chunk_id
chunk_embeddings.doc_id
chunk_embeddings.version_id
```

These are polymorphic references resolved by discriminator fields such as `entity_type` or `doc_kind`.

## 4. Entity Relationship Graph

```text
institutions
├── users
│   ├── user_roles
│   ├── refresh_sessions
│   ├── teaching_assignments
│   ├── quiz_releases
│   ├── audit_events
│   └── chat_conversations
├── student_profiles
│   ├── student_grade_enrollments
│   │   ├── sections
│   │   └── period_grades
│   │       ├── academic_periods
│   │       └── grades
│   └── student_subject_enrollments
│       └── grade_subject_offerings
│           ├── subjects
│           └── topics
│               └── subtopics
│                   ├── source_materials
│                   ├── learning_outcomes
│                   ├── questions
│                   └── common_mastery_quizzes
└── knowledge_documents
    └── knowledge_document_versions
        └── knowledge_chunks

common_mastery_quizzes
└── quiz_versions
    ├── quiz_releases
    ├── quiz_attempts
    │   └── attempt_answers
    ├── quiz_items
    │   └── question_versions
    └── quiz_material_bindings
```

Machine-friendly relationship list: see the complete edge list in section 3. It is the authoritative relationship list for this report.

## 5. Important Entity Relationships

- **Student:** `student_profiles.id` is the canonical student identifier. `users.id` is a login account identifier. The optional link is `student_profiles.user_id → users.id`.
- **Student → Grade:** `student_profiles → student_grade_enrollments → period_grades → grades`.
- **Student → Section:** `student_profiles → student_grade_enrollments → sections`; section is nullable.
- **Student → Subject:** `student_profiles → student_subject_enrollments → grade_subject_offerings → subjects`.
- **Teacher → Subject:** `users → teaching_assignments → grade_subject_offerings → subjects`.
- **Teacher → Students:** derived through assignments plus subject or section enrollments; no direct teacher-student FK exists.
- **Attempt → Quiz:** `quiz_attempts → quiz_versions → common_mastery_quizzes`.
- **Quiz → Subject:** branch on `quiz_scope`.
  - Subtopic: `common_mastery_quizzes → subtopics → topics → grade_subject_offerings → subjects`.
  - Topic: `common_mastery_quizzes → topics → grade_subject_offerings → subjects`.
- **Quiz → Questions:** `common_mastery_quizzes → quiz_versions → quiz_items → question_versions → questions`.
- **Attempt → Answers:** `quiz_attempts → attempt_answers → question_versions`.
- **Attempt → Score:** scores and timestamps are stored on `quiz_attempts`; no separate score table exists.
- **Mastery:** `student_360` exposes pre-aggregated mastery fields, but aggregation semantics require confirmation.

## 6. Canonical Join Paths

### Student → Subject

```text
student_profiles
→ student_subject_enrollments
→ grade_subject_offerings
→ subjects
```

Use the explicit enrollment and offering FKs. Do not join students directly to subjects.

### Student → Grade

```text
student_profiles
→ student_grade_enrollments
→ period_grades
→ grades
```

`period_grades` is mandatory; there is no direct grade-to-offering FK.

### Teacher → Students

```text
users
→ teaching_assignments
→ grade_subject_offerings
← student_subject_enrollments
← student_profiles
```

Use `DISTINCT` or `EXISTS` when assignment multiplicity should not duplicate students.

### Quiz → Subject

```text
subtopic_mastery → subtopics → topics → grade_subject_offerings → subjects
topic_mastery → topics → grade_subject_offerings → subjects
```

Branch on `quiz_scope`; never assume `subtopic_id` is populated.

### Quiz → Questions

```text
common_mastery_quizzes
→ quiz_versions
→ quiz_items
→ question_versions
→ questions
```

Use released/published lifecycle filters where the question concerns learner-visible content.

## 7. Dangerous / Ambiguous Joins

### Wrong quiz-to-offering join

```sql
-- WRONG
grade_subject_offerings.id = common_mastery_quizzes.subtopic_id
```

Correct subtopic path:

```sql
common_mastery_quizzes.subtopic_id = subtopics.id
subtopics.topic_id = topics.id
topics.grade_subject_offering_id = grade_subject_offerings.id
```

Correct topic path:

```sql
common_mastery_quizzes.topic_id = topics.id
topics.grade_subject_offering_id = grade_subject_offerings.id
```

The wrong join compares unrelated UUIDs and silently returns no matches.

### Wrong grade-to-offering join

```sql
-- WRONG
grades.id = grade_subject_offerings.period_grade_id

-- CORRECT
grades.id = period_grades.grade_id
period_grades.id = grade_subject_offerings.period_grade_id
```

### Wrong identity join

```sql
-- WRONG
student_profiles.id = users.id

-- CORRECT
student_profiles.user_id = users.id
```

### Wrong topic/subtopic join

```sql
-- WRONG
topics.id = common_mastery_quizzes.subtopic_id

-- CORRECT
common_mastery_quizzes.subtopic_id = subtopics.id
subtopics.topic_id = topics.id
```

### Quiz scope omission

```text
subtopic_mastery → subtopic_id populated, topic_id NULL
topic_mastery → topic_id populated, subtopic_id NULL
```

This XOR rule is database-enforced.

### Duplicate-producing joins

- `teaching_assignments` can have multiple rows for one teacher/offering, often one per section.
- `quiz_attempts` can have multiple rows for one student/quiz because of `attempt_number`.
- Use `COUNT(DISTINCT student_profiles.id)`, `DISTINCT`, grouping, or `EXISTS` when the repeated side is not part of the answer.

### Nullable relationships

Nullable FKs include `student_profiles.user_id`, assignment/enrollment/attendance `section_id`, attendance subject offering and recorder, quiz release publisher, quiz attempt release and subject enrollment, and both ingest-job target FKs. Use `LEFT JOIN` when records without those relationships must remain.

### Versioned entities

```text
common_mastery_quizzes → quiz_versions
questions → question_versions
source_materials → source_material_versions
knowledge_documents → knowledge_document_versions
```

Filter lifecycle status for current learner-visible content rather than selecting an arbitrary version.

### Security-sensitive joins

`question_answer_keys` contains correct answers and scoring data. It must not appear in student-facing query results.

## 8. Business Semantics That Need Documentation

Supported by structure or application usage:

- `score_percent`: numeric percentage, apparently on a 0–100 scale.
- `pass_threshold_percent`: numeric passing threshold.
- `passed`: stored pass/fail result.
- `submitted_at`: submission timestamp; `scored_at`: scoring timestamp.
- `attempt_number`: distinguishes repeated attempts.
- `quiz_scope`: topic versus subtopic target.
- `lifecycle_status`: version visibility and release state.
- `student_subject_enrollments`: student membership in subject offerings.
- `teaching_assignments`: teacher assignment to offerings and optional sections.

**UNKNOWN / REQUIRES BUSINESS CONFIRMATION:**

- Whether “latest score” means latest submitted, latest scored, or highest score.
- Which timestamp defines “last quiz.”
- Whether archived, withdrawn, inactive, and draft rows are excluded by default.
- Whether `score_percent` or `passed` is authoritative if inconsistent.
- How multiple attempts contribute to mastery.
- How topic-scoped quizzes contribute to subtopic mastery.
- Exact definitions of “completed,” “struggling,” and “at risk.”
- Whether `student_360` is canonical or an optimization view.

## 9. Important Analytical Paths

- **Who took the last quiz in Mathematics?** `student_profiles → quiz_attempts → quiz_versions → common_mastery_quizzes → scope branch → grade_subject_offerings → subjects`; use `submitted_at` only if “took” means submitted.
- **Latest student score:** `student_profiles → quiz_attempts`; order by the business-approved timestamp and handle null scores.
- **Students struggling in Mathematics:** `student_profiles → student_subject_enrollments → grade_subject_offerings → subjects → quiz_attempts`; the threshold and attempt aggregation need confirmation.
- **How many students do I teach?** `users → teaching_assignments → grade_subject_offerings ← student_subject_enrollments ← student_profiles`; count distinct students.
- **Performance by subject:** assignment/offering/subject path plus student enrollment and attempts; define latest-versus-all-attempt behavior.
- **Students at risk:** use `student_360`, attendance, quiz attempts, and material progress; “at risk” is not database-defined.
- **Topics a student struggles with:** attempts → versions → mastery quiz, then branch on topic/subtopic scope.
- **Students without completed quizzes:** define completion first, then prefer `NOT EXISTS` to avoid duplicate rows.

## 10. Text-to-SQL Metadata Requirements

- **Physical schema:** every table, column, type, nullability, primary key, unique constraint, and lifecycle field.
- **FK relationships:** every direct edge, with nullable flags and the two quiz target branches.
- **Entity descriptions:** distinguish `student_profiles` from `users`, `subjects` from offerings, and `topics` from `subtopics`.
- **Business definitions:** define latest, mastery, current term, released, completed, struggling, and at risk.
- **Canonical paths:** provide explicit student, teacher, enrollment, quiz, attempt, question, and progress routes.
- **Forbidden joins:** explicitly forbid `cmq.subtopic_id = gso.id`, `gso.period_grade_id = grades.id`, `student_profiles.id = users.id`, and `cmq.topic_id = subtopics.id`.
- **Business rules:** document XOR quiz targets, nullable links, repeated attempts, lifecycle filters, and answer-key restrictions.
- **Terminology:** map “student” to `student_profiles`, “login account” to `users`, “class” to `sections`, and specific concepts to `subtopics` where confirmed.
- **Examples:** include both topic-scoped and subtopic-scoped quiz examples.
- **Ambiguity rules:** require explicit handling of latest, completed, topic, student, and attempts-versus-distinct-students.

## 11. Verified Facts vs Inferences

### VERIFIED

- The direct FK edges in section 3 exist in PostgreSQL.
- There are no composite FKs.
- Quiz target columns are mutually exclusive by database check constraint.
- `grade_subject_offerings` references `period_grades`, not `grades`.
- `student_profiles.user_id` and several operational links are nullable.
- `audit_events.entity_id` and `chunk_embeddings` identifiers are not formal FKs.
- There are no native PostgreSQL enum types.

### INFERRED FROM STRUCTURE OR APPLICATION USAGE

- Topics are broad curriculum groupings and subtopics are specific concepts.
- `student_360` is intended for analytics.
- `score_percent` represents a 0–100 percentage.
- Teacher-to-student is a derived relationship from assignments and enrollments.
- Released/published lifecycle values represent learner-visible content.

### UNKNOWN / REQUIRES BUSINESS CONFIRMATION

- Exact meanings of latest, completed, struggling, and at risk.
- Default status filters.
- Attempt aggregation rules for mastery and performance.
- Whether `student_360` should be the default analytical source.

## 12. Open Questions / Business Decisions Required

1. Is `submitted_at` or `scored_at` the canonical performance timestamp?
2. Should latest-score queries ignore unscored attempts?
3. Should archived and withdrawn enrollments be excluded automatically?
4. Should analytics use `student_360` by default?
5. How do topic-scoped quizzes contribute to subtopic mastery?
6. How do subtopic-scoped quizzes contribute to topic mastery?
7. Is the active academic period always the current term?
8. Should only the latest attempt count toward performance?
9. What threshold defines struggling?
10. What evidence defines at risk?
11. Should students without login accounts appear in teacher reports?
12. Which polymorphic `entity_type` and `doc_kind` values are supported?

## 13. Recommended Metadata Catalogue Structure

```text
1. Database conventions
2. Tenant and identity model
3. Academic hierarchy
4. Enrollment and teaching model
5. Quiz and assessment model
6. Versioning and lifecycle model
7. Materials and knowledge model
8. Attendance and progress model
9. Complete table/column catalogue
10. Complete FK map
11. Nullable-FK rules
12. Unique and duplicate-row rules
13. Canonical join paths
14. Forbidden joins
15. Polymorphic non-FK references
16. Status and lifecycle values
17. Business terminology
18. Analytical query recipes
19. Ambiguity rules
20. Security restrictions
```

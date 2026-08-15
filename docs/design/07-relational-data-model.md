# Relational Data Model

## 1. Scope

This document is the implementation-level schema contract for the student-evaluation POC. It
reconciles:

- [Identity, tenancy, and authorization](./02-identity-tenancy-and-authorization.md)
- [Academic structure, enrollment, and timetable](./03-academic-structure-enrollment-and-timetable.md)
- [Material lifecycle](./04-material-lifecycle-and-ai-artifacts.md)
- [Assessment: common subtopic mastery quizzes](./05-assessment-common-subtopic-mastery-quizzes.md)

It defines tables, keys, lifecycle fields, uniqueness rules, and integrity invariants that the
Postgres / SQLAlchemy / Alembic foundation must enforce.

### Engine choice (POC)

- **PostgreSQL + pgvector** via Compose (`pgvector/pgvector:pg16`), default URL
  `postgresql+asyncpg://education:education@localhost:5432/education`.
- Sync tools (Alembic, seed, ARQ worker) use `postgresql+psycopg://...`.
- Enums stored as VARCHAR values (`native_enum=False`).
- JSON columns use SQLAlchemy `JSON` (not Postgres JSONB).
- Partial unique indexes use Postgres `WHERE` clauses (`postgresql_where`).
- Teaching-assignment uniqueness with nullable `section_id` uses two partial unique indexes
  (with/without section) instead of Postgres `NULLS NOT DISTINCT`.
- Chunk embeddings live in `chunk_embeddings` (`vector(384)`); exact cosine search for POC volume.


### In this foundation milestone

- Schema design document (this file)
- ORM models and Alembic migrations
- Dockerized Postgres + pgvector
- Database integrity tests

### Deferred to later slices

- Replacing the file-backed materials API with database reads
- JWT login / refresh routes
- Admin publish / release workflows
- Object storage (MinIO/S3) for blobs
- Seeding current `docs/curriculum/` files into grade/subject/topic rows
- Timetable, AI artifacts, evaluation snapshots, and peer analytics tables

## 2. Cross-cutting conventions

| Convention | Choice |
| --- | --- |
| Primary keys | UUID v4 |
| Timestamps | `created_at` / `updated_at` as `timestamptz`, UTC |
| Soft lifecycle | Prefer status fields over hard deletes for learning history |
| Naming | `snake_case` tables and columns |
| Enums | VARCHAR values via SQLAlchemy `Enum(native_enum=False)` |
| Tenant boundary | Every operational row belongs to one institution, directly or through a parent |
| Answer keys | Stored only in `question_answer_keys`; student queries never join that table |
| Engine | PostgreSQL + pgvector (Compose) |
| Cross-row business rules | Enforced in transactional services (not database triggers) when they span multiple entities |

## 3. Entity-relationship overview

```mermaid
erDiagram
    Institution ||--o{ User : owns
    User ||--o{ UserRole : has
    User ||--o| StudentProfile : links
    User ||--o{ RefreshSession : sessions
    Institution ||--o{ AuditEvent : records
    Institution ||--o{ AcademicPeriod : runs
    Institution ||--o{ Grade : defines
    Institution ||--o{ Subject : defines
    AcademicPeriod ||--o{ PeriodGrade : offers
    Grade ||--o{ PeriodGrade : referenced
    PeriodGrade ||--o{ Section : groups
    PeriodGrade ||--o{ GradeSubjectOffering : contains
    Subject ||--o{ GradeSubjectOffering : referenced
    GradeSubjectOffering ||--o{ Topic : organizes
    Topic ||--o{ Subtopic : contains
    Subtopic ||--o{ LearningOutcome : measures
    StudentProfile ||--o{ StudentGradeEnrollment : enrolls
    PeriodGrade ||--o{ StudentGradeEnrollment : hosts
    StudentGradeEnrollment ||--o{ StudentSubjectEnrollment : permits
    GradeSubjectOffering ||--o{ StudentSubjectEnrollment : opens
    User ||--o{ TeachingAssignment : teaches
    GradeSubjectOffering ||--o{ TeachingAssignment : scopes
    Subtopic ||--o{ SourceMaterial : owns
    SourceMaterial ||--o{ SourceMaterialVersion : versions
    Subtopic ||--o{ CommonMasteryQuiz : assesses
    CommonMasteryQuiz ||--o{ QuizVersion : versions
    QuizVersion ||--o{ QuizItem : orders
    Question ||--o{ QuestionVersion : versions
    QuestionVersion ||--o{ QuestionOption : options
    QuestionVersion ||--o| QuestionAnswerKey : key
    QuizVersion ||--o{ QuizAttempt : receives
    QuizAttempt ||--o{ AttemptAnswer : records
```

## 4. Identity and tenancy

### 4.1 `institutions`

| Column | Type | Notes |
| --- | --- | --- |
| id | UUID PK | |
| name | varchar(200) | Unique |
| timezone | varchar(64) | IANA timezone, default `UTC` |
| status | enum | `active`, `archived` |
| created_at / updated_at | timestamptz | |

### 4.2 `users`

| Column | Type | Notes |
| --- | --- | --- |
| id | UUID PK | |
| institution_id | UUID FK → institutions | Indexed |
| email | varchar(320) | Unique **within institution** |
| full_name | varchar(200) | |
| password_hash | text | Argon2/bcrypt hash when auth is wired |
| status | enum | `provisioned`, `active`, `deactivated`, `archived` |
| created_at / updated_at | timestamptz | |

Constraints:

- `UNIQUE (institution_id, email)`

### 4.3 `user_roles`

A user may hold multiple roles. Teacher authority is further narrowed by teaching assignments;
student authority is narrowed by enrollments.

| Column | Type | Notes |
| --- | --- | --- |
| id | UUID PK | |
| user_id | UUID FK → users | Indexed |
| role | enum | `administrator`, `teacher`, `student` |
| created_at / updated_at | timestamptz | |

Constraints:

- `UNIQUE (user_id, role)`

### 4.4 `student_profiles`

Exactly one student profile per student user account.

| Column | Type | Notes |
| --- | --- | --- |
| id | UUID PK | |
| institution_id | UUID FK → institutions | Indexed |
| user_id | UUID FK → users | Unique, nullable until login is provisioned |
| student_identifier | varchar(100) | Institution-scoped roster id |
| full_name | varchar(200) | |
| status | enum | `active`, `inactive`, `archived` |
| created_at / updated_at | timestamptz | |

Constraints:

- `UNIQUE (institution_id, student_identifier)`
- `UNIQUE (user_id)` where `user_id` is not null

### 4.5 `refresh_sessions`

| Column | Type | Notes |
| --- | --- | --- |
| id | UUID PK | |
| user_id | UUID FK → users | Indexed |
| token_hash | varchar(64) | Unique |
| expires_at | timestamptz | |
| revoked_at | timestamptz nullable | |
| created_at / updated_at | timestamptz | |

### 4.6 `audit_events`

Append-only audit trail. Prefer insert-only access from application code.

| Column | Type | Notes |
| --- | --- | --- |
| id | UUID PK | |
| institution_id | UUID FK → institutions | Indexed |
| actor_user_id | UUID FK → users nullable | System actions may be null |
| event_type | varchar(100) | |
| entity_type | varchar(100) | |
| entity_id | UUID nullable | |
| payload | jsonb | Structured details |
| created_at | timestamptz | No `updated_at`; rows are immutable |

## 5. Academic structure

### 5.1 Reusable references

**`grades`** — institution-scoped labels such as Grade 8.

| Column | Notes |
| --- | --- |
| institution_id, name, sort_order | `UNIQUE (institution_id, name)` |

**`subjects`** — institution-scoped disciplines such as Mathematics.

| Column | Notes |
| --- | --- |
| institution_id, name, code | `UNIQUE (institution_id, code)` |

### 5.2 `academic_periods`

| Column | Type | Notes |
| --- | --- | --- |
| institution_id | UUID FK | |
| name | varchar(200) | e.g. `2026–27` |
| start_date / end_date | date | |
| status | enum | `planned`, `active`, `closed`, `archived` |

Constraints:

- `UNIQUE (institution_id, name)`
- Partial unique index: at most one row with `status = 'active'` per institution

### 5.3 Period offerings

**`period_grades`** — grade offered in a period.

- `UNIQUE (academic_period_id, grade_id)`

**`sections`** — optional reporting group under a period grade.

- `UNIQUE (period_grade_id, name)`
- Sections do **not** gate common material or quiz access

**`grade_subject_offerings`** — curriculum and enrollment context for a period.

- FK to `period_grade` and `subject`
- `UNIQUE (period_grade_id, subject_id)`

### 5.4 Curriculum folders

**`topics`** under a grade–subject offering:

- `name`, `slug`, `sequence`
- `UNIQUE (grade_subject_offering_id, slug)`
- `UNIQUE (grade_subject_offering_id, sequence)`

**`subtopics`** under a topic:

- `name`, `slug`, `sequence`
- `UNIQUE (topic_id, slug)`
- `UNIQUE (topic_id, sequence)`
- Owns source materials and the common mastery quiz

**`learning_outcomes`** under a subtopic:

- `code`, `statement`, `sequence`
- `UNIQUE (subtopic_id, code)`

## 6. Enrollments and teaching assignments

### 6.1 `student_grade_enrollments`

| Column | Notes |
| --- | --- |
| student_id | FK → student_profiles |
| academic_period_id | FK → academic_periods |
| period_grade_id | FK → period_grades |
| section_id | optional FK → sections |
| status | `active`, `withdrawn` |

Constraints:

- Partial unique: one **active** grade enrollment per `(student_id, academic_period_id)`
- `period_grade.academic_period_id` must match `academic_period_id` (service-enforced on write; also
  denormalized period id kept for query clarity)
- If `section_id` is set, section must belong to the same `period_grade_id`

### 6.2 `student_subject_enrollments`

| Column | Notes |
| --- | --- |
| student_id | FK → student_profiles |
| grade_enrollment_id | FK → student_grade_enrollments |
| grade_subject_offering_id | FK → grade_subject_offerings |
| status | `active`, `withdrawn` |

Constraints:

- Partial unique: one **active** subject enrollment per `(student_id, grade_subject_offering_id)`
- Offering’s `period_grade_id` must match the grade enrollment’s `period_grade_id`

Authorization formula for learner content:

```text
active institution
+ active academic period
+ active StudentGradeEnrollment
+ active StudentSubjectEnrollment
+ published source / released quiz version
```

### 6.3 `teaching_assignments`

| Column | Notes |
| --- | --- |
| teacher_user_id | FK → users |
| academic_period_id | FK → academic_periods |
| grade_subject_offering_id | FK → grade_subject_offerings |
| section_id | optional FK → sections |
| status | `active`, `ended` |

Constraints:

- Two partial unique indexes:
  - `(teacher_user_id, grade_subject_offering_id, section_id)` where `section_id IS NOT NULL`
  - `(teacher_user_id, grade_subject_offering_id)` where `section_id IS NULL`
- Teacher must hold the `teacher` role (service-enforced)

## 7. Source materials

### 7.1 `source_materials`

Leaf under a subtopic.

| Column | Notes |
| --- | --- |
| subtopic_id | FK |
| title | |
| slug | unique within subtopic |
| status | `draft`, `published`, `archived` |

### 7.2 `source_material_versions`

Immutable once published.

| Column | Notes |
| --- | --- |
| source_material_id | FK |
| version_number | positive integer |
| lifecycle_status | `draft`, `processing`, `ready`, `published`, `failed`, `superseded`, `archived` |
| title | |
| content_markdown | text nullable — approved inline content for POC |
| content_format | varchar — e.g. `markdown`, `plain` |
| blob_object_key | nullable — reserved for later object storage |
| blob_content_type | nullable |
| checksum | nullable |
| failure_reason | nullable |
| published_at | nullable |

Constraints:

- `UNIQUE (source_material_id, version_number)`
- Partial unique: at most one `published` version per material at a time (superseded versions keep
  historical status)

Runtime note: until a later migration slice, `docs/curriculum/*.md` remains the live approved source
for the materials API. This schema stores the target shape; no guessed grade/subject mappings are
seeded from those files in this milestone.

## 8. Assessment

### 8.1 Questions

**`questions`** — stable identity under a subtopic.

**`question_versions`** — immutable published item content.

| Column | Notes |
| --- | --- |
| question_id | FK |
| version_number | unique per question |
| prompt | text |
| question_type | `multiple_choice`, `true_false`, `matching`, `numeric` |
| difficulty | nullable `easy`, `medium`, `hard` |
| marks | numeric |
| explanation | student-safe explanation, nullable |
| lifecycle_status | `draft`, `published`, `archived` |

**`question_options`** — labels and text for objective choices.

- `UNIQUE (question_version_id, label)`

**`question_answer_keys`** — server-only correct answers.

| Column | Notes |
| --- | --- |
| question_version_id | unique FK |
| correct_option_label | nullable for MC |
| correct_boolean | nullable for true/false |
| correct_numeric | nullable for numeric |
| correct_mapping | jsonb nullable for matching |
| scoring_rubric | jsonb nullable |

Student-facing reads must select question versions and options **without** joining
`question_answer_keys`.

**`question_outcome_tags`** — many-to-many between question versions and learning outcomes.

- `UNIQUE (question_version_id, learning_outcome_id)`
- Every published question version should have ≥1 tag (service-enforced)

### 8.2 Common mastery quizzes

**`common_mastery_quizzes`** — one quiz identity per subtopic.

- `UNIQUE (subtopic_id)` for the POC (one common quiz per subtopic)

**`quiz_versions`**

| Column | Notes |
| --- | --- |
| quiz_id | FK |
| version_number | unique per quiz |
| lifecycle_status | `draft`, `ready`, `released`, `archived` |
| duration_seconds | nullable |
| max_attempts | nullable |
| result_release_mode | `immediate`, `admin_release` |
| released_at | nullable |

**`quiz_items`** — ordered binding of question versions into a quiz version.

- `UNIQUE (quiz_version_id, sequence)`
- `UNIQUE (quiz_version_id, question_version_id)`

**`quiz_material_bindings`** — which published material version(s) this quiz release covers.

- `UNIQUE (quiz_version_id, source_material_version_id)`

**`quiz_releases`** — optional explicit release window record.

| Column | Notes |
| --- | --- |
| quiz_version_id | FK |
| window_starts_at / window_ends_at | nullable |
| released_by_user_id | FK → users |
| status | `scheduled`, `open`, `closed` |

Service rule: a quiz version may move to `released` only when its subtopic has at least one
published `source_material_version` and bindings are recorded.

### 8.3 Attempts

**`quiz_attempts`**

| Column | Notes |
| --- | --- |
| student_id | FK → student_profiles |
| quiz_version_id | FK |
| attempt_number | positive integer |
| status | `not_started`, `in_progress`, `submitted`, `expired`, `scored`, `released`, `held` |
| started_at / submitted_at / scored_at | nullable |
| score_raw / score_percent | nullable |
| passed | nullable boolean |

Constraints:

- `UNIQUE (student_id, quiz_version_id, attempt_number)`

**`attempt_answers`**

| Column | Notes |
| --- | --- |
| attempt_id | FK |
| question_version_id | FK |
| selected_option_label / boolean / numeric / mapping | response payload |
| is_correct | nullable until scored |
| marks_awarded | nullable |

Constraints:

- `UNIQUE (attempt_id, question_version_id)`

Scored attempts and their answers are historically immutable except through audited corrections
(future workflow).

## 9. Integrity invariants checklist

Database-enforced:

1. Email unique per institution.
2. One role row per `(user, role)`.
3. One student profile per user; student identifier unique per institution.
4. At most one active academic period per institution.
5. Unique period grade, offering, topic/subtopic slug and sequence among siblings.
6. One active grade enrollment per student per period.
7. One active subject enrollment per student per offering.
8. Unique material and quiz version numbers; unique published material version.
9. Answer keys isolated in their own table with 1:1 question version link.
10. Attempt and answer uniqueness as above; FK history retained.

Service-enforced (transactional):

1. Subject enrollment’s offering shares the grade enrollment’s period grade.
2. Section (if set) belongs to the enrollment’s period grade.
3. Teacher assignments require the teacher role.
4. Quiz release requires published material and recorded bindings.
5. Published question versions have ≥1 learning-outcome tag.
6. Student content APIs never load `question_answer_keys`.
7. Deactivating a user revokes refresh sessions immediately.

## 10. Module mapping

| Domain | Package | Tables |
| --- | --- | --- |
| Identity | `education_platform.modules.auth.models` | institutions, users, user_roles, student_profiles, refresh_sessions, audit_events |
| Academics | `education_platform.modules.academics.models` | grades, subjects, academic_periods, period_grades, sections, grade_subject_offerings, topics, subtopics, learning_outcomes, enrollments, teaching_assignments |
| Materials | `education_platform.modules.materials.models` | source_materials, source_material_versions |
| Assessments | `education_platform.modules.assessments.models` | questions, versions, options, answer keys, outcome tags, quizzes, quiz versions/items/bindings/releases, attempts, answers |

Shared declarative base and naming conventions live in `education_platform.db.base`.

## 11. Acceptance criteria for this foundation

1. Design document matches implemented ORM models and the initial migration.
2. `alembic upgrade head` creates the full schema on a clean Postgres database.
3. Integrity tests cover tenant email uniqueness, single active period, enrollment uniqueness,
   version uniqueness, answer-key isolation, and attempt FK history.
4. Existing materials API tests continue to pass unchanged.
5. CI runs Alembic upgrade against Postgres (`education_test`) before pytest.

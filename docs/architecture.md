# Architecture

Target-design diagrams. Narrative overview: [project-overview.html](./project-overview.html).
Component detail: [design docs](./design/README.md).

| View | Design |
| --- | --- |
| Context / components | [00 abstract system view](./design/00-abstract-system-view.md) |
| Student directory | [01 student learning experience](./design/01-student-learning-experience.md) |
| Identity / auth gate | [02 identity tenancy authorization](./design/02-identity-tenancy-and-authorization.md) |
| Academic structure | [03 academic structure enrollment](./design/03-academic-structure-enrollment-and-timetable.md) |
| Source / material lifecycle | [04 material lifecycle](./design/04-material-lifecycle-and-ai-artifacts.md) |
| Assessment | [05 common mastery quizzes](./design/05-assessment-common-subtopic-mastery-quizzes.md) |
| Analytics | [06 analytics comparison](./design/06-analytics-and-comparison-insights.md) |

## 1. System context

```mermaid
flowchart LR
    Web[ReactWebApp]
    Mobile[ReactNativeApp]
    Admin[Administrator]
    Teacher[Teacher]
    Student[Student]

    subgraph Platform[EducationPlatform]
        Api[FastAPI_OpenAPI]
        Tenant[InstitutionTenant]
    end

    Admin --> Web
    Teacher --> Web
    Student --> Web
    Student --> Mobile
    Teacher --> Mobile
    Web -->|JWT_REST| Api
    Mobile -->|JWT_REST| Api
    Api --> Tenant
```

## 2. Bounded components

```mermaid
flowchart TB
    Identity[IdentityAndAccess]
    Academic[AcademicStructure]
    Source[SourceCurriculum]
    Ingestion[IngestionAndIndexing]
    Assessment[Assessment]
    Analytics[AnalyticsAndInsights]
    StudentUX[StudentLearningExperience]
    Infra[PlatformInfrastructure]
    AiAssist[GroundedAI]

    Identity --> Academic
    Academic --> Source
    Academic --> StudentUX
    Source --> Ingestion
    Source --> Assessment
    Source --> StudentUX
    Assessment --> Analytics
    Analytics --> StudentUX
    Identity --> StudentUX
    Identity --> Assessment
    Identity --> AiAssist
    Source --> AiAssist
    Ingestion --> AiAssist
    Infra --> Identity
    Infra --> Academic
    Infra --> Source
    Infra --> Ingestion
    Infra --> Assessment
    Infra --> Analytics
    Infra --> AiAssist
```

## 3. Two directories

```mermaid
flowchart TB
    subgraph SourceCurriculum[SourceCurriculum_shared]
        Period[AcademicPeriod]
        Grade[Grade]
        Subject[Subject]
        Topic[Topic]
        Subtopic[Subtopic]
        MatVer[SourceMaterialVersions]
        QuizVer[CommonMasteryQuiz]
        Period --> Grade --> Subject --> Topic --> Subtopic
        Subtopic --> MatVer
        Subtopic --> QuizVer
    end

    subgraph StudentLearningDirectory[StudentLearningDirectory_private]
        SPeriod[AcademicPeriod]
        SGrade[Grade]
        SSubject[Subject]
        STopic[Topic]
        SSubtopic[Subtopic]
        Ref[SourceMaterialReference]
        Progress[MaterialProgress]
        Attempts[MasteryQuizAttempts]
        Snapshots[EvaluationSnapshots]
        SPeriod --> SGrade --> SSubject --> STopic --> SSubtopic
        SSubtopic --> Ref
        SSubtopic --> Progress
        SSubtopic --> Attempts
        SSubtopic --> Snapshots
    end

    MatVer -.->|reference_not_copy| Ref
    QuizVer -.->|same_published_version| Attempts
```

## 4. Authorization gate

```mermaid
flowchart TD
    Req[ProtectedRequest] --> AuthN{Authenticated_active?}
    AuthN -->|no| Deny[Deny_audit]
    AuthN -->|yes| Inst{Same_institution?}
    Inst -->|no| Deny
    Inst -->|yes| Period{Period_permits?}
    Period -->|no| Deny
    Period -->|yes| Role{Role_and_scope?}
    Role -->|no| Deny
    Role -->|yes| Enroll{Grade_and_GradeSubject_enrollment?}
    Enroll -->|no| Deny
    Enroll -->|yes| Life{Published_or_released?}
    Life -->|no| Deny
    Life -->|yes| Resolve[Resolve_content]
```

## 5. Study to evaluation pipeline

```mermaid
flowchart TD
    AdminSetup[Admin_enrollments] --> Publish
    AdminUpload[Admin_publish_material_and_quiz] --> Publish
    Publish --> OpenDir[Student_opens_directory]
    OpenDir --> Study[Study_published_material]
    Study --> Attempt[Submit_common_subtopic_quiz]
    Attempt --> Score[Auto_objective_scoring]
    Score --> Snapshot[EvaluationSnapshot]
    Snapshot --> StudentView[Four_pillar_student_view]
    Snapshot --> TeacherView[Teacher_class_insights]
```

## 6. Request lifecycle

```mermaid
sequenceDiagram
    participant Student
    participant Api as API
    participant Access as AccessService
    participant Curriculum as CurriculumService
    participant Store as ContentStore
    participant Assessment as AssessmentService
    participant Metrics as MetricsService

    Student->>Api: RequestSubtopicMaterial
    Api->>Access: ValidateTokenInstitutionGradeSubject
    Access-->>Api: ActiveEnrollmentConfirmed
    Api->>Curriculum: ResolvePublishedMaterial
    Curriculum->>Store: ReadPublishedVersion
    Store-->>Api: MaterialPayload
    Api-->>Student: MaterialAndProgressState

    Student->>Api: SubmitSubtopicQuiz
    Api->>Access: ValidateQuizAccess
    Api->>Assessment: ValidateAttemptAndScoreAnswers
    Assessment->>Metrics: PersistScoreAndOutcomeEvidence
    Metrics->>Metrics: CalculateFourPillars
    Metrics-->>Api: EvaluationSnapshot
    Api-->>Student: ScoreAndEvaluation
```

## 7. Material lifecycle

```mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> Processing: UploadAccepted
    Processing --> Ready: IngestionSucceeds
    Processing --> Failed: IngestionFails
    Failed --> Draft: CorrectAndReupload
    Ready --> Published: AdminPublishes
    Published --> Superseded: NewerVersionPublished
    Published --> Archived
    Superseded --> Archived
```

## 8. Quiz attempt lifecycle

```mermaid
stateDiagram-v2
    [*] --> NotStarted
    NotStarted --> InProgress: StartAttempt
    InProgress --> Submitted: StudentSubmits
    InProgress --> Expired: TimerEnds
    Submitted --> Scored: AutoScore
    Expired --> Scored: AutoScoreLockedAnswers
    Scored --> Released: ResultsVisible
    Scored --> Held: AwaitAdminRelease
    Held --> Released: ResultsReleased
    Released --> Invalidated: AuditedCorrection
```

## 9. Infrastructure

```mermaid
flowchart TB
    subgraph Clients[Clients]
        Web[ReactWebApp]
        Mobile[ReactNativeApp]
    end

    subgraph App[Application]
        Api[FastAPI]
        Worker[IngestionWorker]
        AiPorts[LLM_Embedding_Ports]
    end

    subgraph Data[Data_plane]
        Pg["PostgreSQL_pgvector"]
        Objects[ObjectStorage]
        Redis[Redis_queue]
    end

    Web --> Api
    Mobile --> Api
    Api --> Pg
    Api --> Objects
    Api --> AiPorts
    Api --> Redis
    Worker --> Redis
    Worker --> Objects
    Worker --> Pg
    Worker --> AiPorts

    LocalDev["Local_dev: SQLite_local_files_in_process"] -.-> Api
    Compose["Compose: Postgres_Redis_MinIO"] -.-> Data
```

## 10. Trust boundaries

```mermaid
flowchart TB
    subgraph Untrusted[Untrusted]
        Client[Client_requests]
        Uploads[Uploaded_files_extracted_text]
        ModelOut[Model_output]
        PeerRaw[Peer_identities_raw_marks]
    end

    subgraph Trusted[Trusted_server_side]
        AuthZ[AuthN_AuthZ_enrollment_checks]
        Policy[Publication_and_release_policy]
        Scoring[Deterministic_objective_scoring]
        Snapshots[Evaluation_snapshots]
        AnonPeer[Anonymized_peer_bands_only]
    end

    Client --> AuthZ
    Uploads --> Policy
    ModelOut --> Policy
    AuthZ --> Scoring
    Scoring --> Snapshots
    Snapshots --> AnonPeer
    PeerRaw -.->|never_exposed_to_students| AnonPeer
    Snapshots -.->|must_not_mutate| SourceCurriculum[SourceCurriculum]
```

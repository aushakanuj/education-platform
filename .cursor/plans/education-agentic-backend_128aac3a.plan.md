---
name: education-agentic-backend
overview: Build a greenfield FastAPI backend foundation for administrator-managed curriculum knowledge bases and teacher-facing grounded AI chat and lesson generation, with portable infrastructure, React / React Native-ready APIs, and reproducible developer tooling. The product design is now student-centric; see docs/design for the learner loop, online assessment, analytics, and parent views that follow this foundation.
todos:
  - id: bootstrap-tooling
    content: Create the uv project, cross-platform setup scripts, local services, pre-commit configuration, and CI quality gates.
    status: pending
  - id: foundation-auth
    content: Implement the FastAPI application foundation, persistence, migrations, institution-aware JWT authentication, RBAC, and audit logging.
    status: pending
  - id: admin-ingestion
    content: Implement administrator curriculum management, object storage, publication workflow, and asynchronous document indexing.
    status: pending
  - id: teacher-rag
    content: Implement assignment-scoped teacher chat, citations, and lesson/content generation through provider-neutral AI interfaces.
    status: pending
  - id: cursor-workflows
    content: Add concise AGENTS.md guidance, one backend verification skill, and a focused RAG reviewer subagent without duplicating CI or pre-commit.
    status: pending
  - id: verify-document
    content: Complete unit/integration/security tests and document setup, architecture, APIs, and the deferred delivery roadmap.
    status: pending
isProject: false
---

# Education Agentic Backend POC

## Confirmed scope
- Backend repository only; expose a versioned REST/OpenAPI contract for separate React web and React Native clients.
- Foundation engineering slice roles: administrator and teacher (curriculum publication and grounded teacher AI).
- Product design POC roles additionally include student, parent, and supervisor; see [`docs/design/00-abstract-system-view.md`](../../docs/design/00-abstract-system-view.md) and [`docs/design/01-student-learning-experience.md`](../../docs/design/01-student-learning-experience.md).
- Only administrators upload, organize, publish, and assign curriculum sources; teachers can query only assigned published content; students later consume only enrollment-scoped published/released content.
- First implemented AI workflows: grounded curriculum chat with citations and lesson/content generation.
- Portable stack: PostgreSQL + pgvector, S3-compatible object storage, Redis-backed worker, and provider-neutral LLM/embedding interfaces. Start with an environment-configured OpenAI-compatible adapter without leaking provider details into domain code.

## 1. Bootstrap the repository and developer experience
- Create [`pyproject.toml`](/Users/aushakanuz/Documents/studies/education-platform/pyproject.toml), [`uv.lock`](/Users/aushakanuz/Documents/studies/education-platform/uv.lock), and [`.python-version`](/Users/aushakanuz/Documents/studies/education-platform/.python-version) around Python 3.12 and uv dependency groups for runtime, development, and testing.
- Add FastAPI, Pydantic Settings, SQLAlchemy/Alembic, PostgreSQL/pgvector, JWT/password hashing, object-storage, worker/Redis, document parsing, and LLM adapter dependencies. Add Ruff, mypy, pytest, coverage, and pre-commit as development tools.
- Extend [`.gitignore`](/Users/aushakanuz/Documents/studies/education-platform/.gitignore) for generated Python, coverage, Ruff/mypy, local storage, and secrets while retaining the existing `.venv/` exclusion.
- Add [`.pre-commit-config.yaml`](/Users/aushakanuz/Documents/studies/education-platform/.pre-commit-config.yaml) for file hygiene plus Ruff lint/fix and formatting; put full type-check and test commands in CI.
- Add idempotent [`scripts/setup-macos.sh`](/Users/aushakanuz/Documents/studies/education-platform/scripts/setup-macos.sh) and [`scripts/setup-windows.ps1`](/Users/aushakanuz/Documents/studies/education-platform/scripts/setup-windows.ps1): install uv from its official installer only when absent, install Python 3.12 through uv, run `uv sync --all-groups`, create `.venv`, install pre-commit hooks, and print next steps without overwriting an existing `.env`.
- Add [`.env.example`](/Users/aushakanuz/Documents/studies/education-platform/.env.example), [`compose.yaml`](/Users/aushakanuz/Documents/studies/education-platform/compose.yaml) for PostgreSQL/pgvector, Redis, and MinIO, and update [`README.md`](/Users/aushakanuz/Documents/studies/education-platform/README.md) with setup and common `uv run` commands.

## 2. Establish the FastAPI architecture
- Use a `src` layout under [`src/education_platform/`](/Users/aushakanuz/Documents/studies/education-platform/src/education_platform/) with `core`, `api/v1`, `db`, `modules`, `ai`, and `workers` boundaries; keep API schemas, application services, persistence, and external adapters separate.
- Implement settings validation, lifespan-managed resources, structured logging, request IDs, consistent error responses, CORS configuration for React web, and health/readiness endpoints.
- Configure async SQLAlchemy and Alembic migrations. Model institution ownership from the start and include users/roles, refresh sessions, curriculum collections, teacher assignments, documents, ingestion jobs, chunks/embeddings, conversations/messages/citations, generated lesson artifacts, and audit events.
- Add backend-managed authentication with Argon2 password hashing, short-lived access JWTs, rotated/revocable refresh tokens, and route-level administrator/teacher authorization.

## 3. Build administrator curriculum management
- Add administrator APIs for teacher account management, curriculum/subject collections, teacher assignments, document upload, processing status, publication, replacement/versioning, and archival.
- Store source files in S3-compatible storage and metadata/state in PostgreSQL. Use explicit `draft -> processing -> ready -> published` states so an uploaded file never becomes teacher-visible accidentally.
- Validate file type, size, ownership, and content boundaries. Begin with text PDFs, DOCX, PPTX, and TXT; record unsupported/scanned documents as clear failures and defer OCR.
- Run parsing, normalization, chunking, embedding, and indexing in a retryable Redis-backed worker. Preserve source filename, page/section, version, checksum, and chunk identifiers for citations and idempotent re-indexing.

## 4. Implement grounded teacher AI workflows
- Add teacher APIs to list assigned published collections, create conversations, ask questions, inspect source citations, and generate structured lesson plans/content.
- Build a retrieval pipeline that filters by institution, teacher assignment, publication state, and selected collection before searching pgvector; combine semantic retrieval with PostgreSQL text search where useful.
- Assemble bounded context, require cited answers, return an explicit insufficient-evidence response when retrieval is weak, and persist prompts, model metadata, citations, latency, and token usage for auditability.
- Use typed LLM and embedding ports with a fake adapter for tests. Keep prompt templates versioned and separate for curriculum Q&A and lesson generation.
- Apply basic prompt-injection defenses: source text is untrusted data, retrieved instructions cannot override system policy, and model output never grants access or triggers privileged actions.

## 5. Add tests, CI, and API documentation
- Create [`tests/`](/Users/aushakanuz/Documents/studies/education-platform/tests/) for unit tests, authenticated API tests, database/storage/worker integration tests, authorization boundaries, ingestion idempotency, citation fidelity, and deterministic AI tests using fakes.
- Add [`.github/workflows/ci.yml`](/Users/aushakanuz/Documents/studies/education-platform/.github/workflows/ci.yml) to run lockfile validation, Ruff, mypy, pytest/coverage, and migration checks on supported platforms.
- Document the architecture, data model, ingestion lifecycle, API usage, environment variables, deployment assumptions, and React / React Native integration contract under [`docs/`](/Users/aushakanuz/Documents/studies/education-platform/docs/).

## 6. Add Cursor-native project guidance and workflows
- There is no supported `agents.d` format. Use [`AGENTS.md`](/Users/aushakanuz/Documents/studies/education-platform/AGENTS.md) for concise repository-wide architecture, dependency, migration, testing, and quality instructions.
- Add one manually invokable [`verify-backend` skill](/Users/aushakanuz/Documents/studies/education-platform/.cursor/skills/verify-backend/SKILL.md) that runs Ruff, mypy, tests, migration validation, and an OpenAPI smoke check in a fixed order.
- Add one specialized [`rag-reviewer` subagent](/Users/aushakanuz/Documents/studies/education-platform/.cursor/agents/rag-reviewer.md) to review retrieval authorization, citation fidelity, prompt-injection boundaries, and deterministic tests. Keep it read-only and evidence-driven.
- Do not add Cursor hooks initially; pre-commit and CI are the deterministic enforcement layers. Introduce [`.cursor/rules/*.mdc`](/Users/aushakanuz/Documents/studies/education-platform/.cursor/rules/) or more skills/subagents only when a stable file-scoped or repeatable workflow emerges.

## POC acceptance flow
1. A fresh macOS or Windows checkout is bootstrapped by one setup script and all quality checks pass.
2. An administrator signs in, creates a teacher and curriculum collection, uploads and publishes a document, and assigns the collection.
3. The worker indexes the document; processing status and failures are visible to the administrator.
4. The teacher signs in, sees only assigned published collections, asks a question, receives a grounded answer with traceable citations, and generates a structured lesson plan.
5. Cross-institution, unassigned, unpublished, and administrator-only resources are rejected and audited.

## Deferred roadmap
Product design documents under `docs/design/` are now the source of truth for sequencing. High-level delivery after this foundation:

- Phase 2: academic structure, student/parent identity, enrollment-scoped module access.
- Phase 3: online quizzes, automatic objective scoring, learner dashboards, and the four performance metric families.
- Phase 4: remediation recommendations, teacher class insights, parent child-progress views.
- Later: adaptive testing, subjective grading, TPO/leadership dashboards, forums, certifications, enterprise SSO, Kubernetes/cloud deployment, backup, disaster recovery, and compliance hardening.
# Education Agentic Platform

FastAPI backend for an institution-aware education platform. The first product POC is a
common-curriculum student-evaluation loop:

- administrators publish a shared SourceCurriculum by Grade → Subject → Topic → Subtopic;
- enrolled students open a private StudentLearningDirectory that references those published
  sources;
- after each subtopic, students take the same common mastery quiz and review four performance
  pillars—marks, anonymized peer context, weak subtopics, and progress over time;
- teachers use assigned-group evidence to support students.

## Product design

The design covers academic periods, Grade and Grade–Subject enrollments, administrator-published
source materials, common subtopic mastery quizzes with automatic objective scoring, and learner
evaluation snapshots. Parent views, teacher-authored material, adaptive practice, and private
dynamic materials are documented as later phases.

See the [HTML project overview](docs/project-overview.html) (open in a browser),
[architecture diagrams](docs/architecture.md), and
[design documentation](docs/design/README.md) for the current source of truth, especially the
[abstract system view](docs/design/00-abstract-system-view.md) and
[student learning experience](docs/design/01-student-learning-experience.md). These documents
describe the planned product; the implementation below currently covers only the initial backend
foundation.

## Current implementation capabilities

- JWT authentication for administrators and teachers
- Administrator-managed teacher accounts, curriculum collections, assignments, documents, and
  publication
- Text, PDF, and DOCX document parsing with source chunks
- Assignment-scoped teacher Q&A with citations and structured lesson-plan generation

## Planned POC capabilities

- Student accounts with Grade and Grade–Subject enrollment-scoped access
- Administrator-published SourceCurriculum folders and materials
- Common mastery quizzes after each subtopic, attempts, and automatic scoring
- Private StudentLearningDirectory progress, attempts, and evaluation snapshots
- Marks, anonymized peer context, subtopic struggle analysis, and progress trends
- Teacher class insights

## Prerequisites

- Docker Desktop (for PostgreSQL, Redis, and MinIO in the portable local stack)
- macOS/Linux: `bash` and `curl`; Windows: PowerShell

## Setup

```bash
# macOS/Linux
./scripts/setup-macos.sh

# Windows PowerShell
./scripts/setup-windows.ps1

docker compose up -d
uv run alembic upgrade head
uv run uvicorn education_platform.main:app --reload
```

Copy `.env.example` to `.env` before starting the app and replace the development JWT secret.
The API documentation is then available at `http://127.0.0.1:8000/docs`.

## Quality checks

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

## Current constraints

The current implementation uses local object storage and in-process document processing for a
simple developer experience. The Docker stack is ready for planned S3-compatible storage and
Redis-backed worker adapters. The broader product design—SourceCurriculum folders,
Grade–Subject enrollment, common subtopic quizzes, and evaluation snapshots—has not yet been
implemented.

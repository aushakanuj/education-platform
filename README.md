# Education Agentic Platform

FastAPI backend for administrator-approved curriculum libraries and teacher-facing grounded
curriculum assistance.

## Product design

The evolving target design covers academic periods, curriculum templates, grades, sections, student
enrollment, timetables, teacher workspaces, topic-scoped question corpora, offline section quiz
variants, and supervisor-approved two-week material and plan batches.

See the [design documentation](docs/design/README.md) for the current source of truth. These
documents describe the planned product; the implementation below currently covers only the initial
backend foundation.

## POC capabilities

- JWT authentication for administrators and teachers
- Administrator-managed teacher accounts, curriculum collections, assignments, documents, and
  publication
- Text, PDF, and DOCX document parsing with source chunks
- Assignment-scoped teacher Q&A with citations and structured lesson-plan generation

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
Redis-backed worker adapters. The broader product design—academic periods, students, timetables,
assessment variants, supervisor reviews, and analytics—has not yet been implemented.

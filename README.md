# Education Agentic Platform

FastAPI backend for administrator-approved curriculum libraries and teacher-facing grounded
curriculum assistance.

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

The initial POC uses local object storage and in-process document processing for a simple
developer experience. The Docker stack is ready for the planned S3-compatible object storage and
Redis-backed worker adapters. Assessment workflows, students, analytics, and production cloud
hardening are intentionally deferred.

# Education Platform

Monorepo for the education platform POC.

- `backend/` — FastAPI API backed by SQLite
- `frontend/` — Vite + React student web client (Hum / Narrative Workflow)
- `docs/materials/` — admin-approved lesson and quiz markdown (seed source)

## Current POC slice

Approved markdown under `docs/materials/` is seeded into SQLite. Authenticated students with
active Grade + Grade–Subject enrollments can list topics, read lessons/quizzes (no answer keys),
and start/submit scored quiz attempts. Auth uses JWT access/refresh tokens.

Browse the schema visually:
[docs/design/relational-schema.html](docs/design/relational-schema.html).

## Prerequisites

- macOS/Linux: `bash` and `curl`; Windows: PowerShell
- Python 3.12 via `uv`

## Setup

```bash
# macOS/Linux
./scripts/setup-macos.sh

# Windows PowerShell
./scripts/setup-windows.ps1
```

Prepare the database and seed curriculum from `backend/`:

```bash
cd backend
uv run alembic upgrade head
uv run python -m education_platform.modules.materials.seed
```

The API also auto-seeds on startup when the database has no topics yet.

Start the API:

```bash
uv run uvicorn education_platform.main:app --reload
```

Open API docs at `http://127.0.0.1:8000/docs`.

### Frontend

```bash
cd frontend
cp .env.example .env   # VITE_API_BASE_URL=http://127.0.0.1:8000
npm install
npm run dev
```

Open `http://localhost:5173`. Create a student (or sign in), enroll in Grade 8 Math, then
study topics and take quizzes.

### Example requests

```bash
# Provision a student (POC helper), login, enroll in seeded Grade 8 Math, then study/attempt
curl -X POST http://127.0.0.1:8000/api/v1/auth/provision-student \
  -H 'Content-Type: application/json' \
  -d '{"email":"student@example.com","password":"password123","full_name":"Asha","student_identifier":"S1"}'
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"student@example.com","password":"password123"}' | python -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
curl -X POST http://127.0.0.1:8000/api/v1/me/enrollments/poc-math -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"confirm":true}'
curl http://127.0.0.1:8000/api/v1/materials -H "Authorization: Bearer $TOKEN"
curl http://127.0.0.1:8000/health
```

## Quality checks

```bash
cd backend
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run alembic upgrade head
uv run pytest
```

## Later

MinIO/S3 (for binary uploads) and richer analytics views will follow as needed.

Product design docs remain under [docs/design/](docs/design/README.md).

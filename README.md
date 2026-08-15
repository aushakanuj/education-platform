# Agentic Education Platform

Multi-role platform for automated education management and analytics. Administrators publish shared
source curriculum; enrolled students study through a private learning directory; teachers consume
class evidence (teacher UI is mock-only in the POC). See the
[documentation hub](docs/README.md) for vision, reading paths, and the full implementation matrix.

## Monorepo layout

- `backend/` — FastAPI API backed by Postgres + pgvector
- `frontend/` — Vite + React multi-role web client (student, admin, teacher mock)
- `docs/curriculum/` — admin-approved lesson and quiz markdown (seed source)
- `docs/` — architecture, design, research, and assets ([hub](docs/README.md))

## Current POC slice

| Role | Flow | Status |
| --- | --- | --- |
| **Student** | Enroll → learning directory → lesson → quiz → score | **Built** |
| **Admin** | JWT login → `/admin/materials` browse (read-only) | **Built** |
| **Teacher** | `/teacher/*` workspace | **Mock** (frontend fixtures only) |

Approved markdown under `docs/curriculum/` is seeded into Postgres. Authenticated students with active
Grade + Grade–Subject enrollments can list topics, read lessons/quizzes (no answer keys), and
start/submit scored quiz attempts. Auth uses JWT access/refresh tokens.

Browse the schema visually:
[docs/design/relational-schema.html](docs/design/relational-schema.html).

### Implementation summary

| Area | Status |
| --- | --- |
| JWT auth + roles | **Built** |
| Enrollment gate + learning directory | **Built** |
| Curriculum seed + student quiz loop | **Built** |
| Admin materials browser | **Built** |
| Teacher workspace / policy assistant | **Partial** (policy chat live; teacher still mock) |
| Four-pillar analytics, ingestion, AI | **Deferred** |

Full matrix: [docs/README.md#implementation-status](docs/README.md#implementation-status).

## Prerequisites

- macOS/Linux: `bash` and `curl`; Windows: PowerShell
- Python 3.12 via `uv`
- Docker (Compose Postgres + pgvector)

## Setup

```bash
# macOS/Linux
./scripts/setup-macos.sh

# Windows PowerShell
./scripts/setup-windows.ps1
```

Start infra, migrate, and seed curriculum:

```bash
docker compose up -d postgres
cd backend
uv run alembic upgrade head
uv run python -m education_platform.modules.materials.seed
```

The API also auto-seeds on startup when the database has no topics yet.

Start the API:

```bash
uv run uvicorn education_platform.main:app --reload
```

For admin PDF ingest, also run the Postgres claim worker:

```bash
uv run python -m education_platform.workers
```

Open API docs at `http://127.0.0.1:8000/docs`.

### Frontend

```bash
cd frontend
cp .env.example .env   # VITE_API_BASE_URL=http://127.0.0.1:8000
npm install
npm run dev
```

Open `http://localhost:5173`. Sign in as a student, enroll in Grade 8 Math, then study topics and
take quizzes. Demo accounts: `student@demo.school` / `demo1234`, `admin@demo.school` / `demo1234`.

### Example requests

**Student** — provision, login, enroll, learning directory:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/provision-student \
  -H 'Content-Type: application/json' \
  -d '{"email":"student@example.com","password":"password123","full_name":"Asha","student_identifier":"S1"}'
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"student@example.com","password":"password123"}' | python -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
curl -X POST http://127.0.0.1:8000/api/v1/me/enrollments/poc-math \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"confirm":true}'
curl http://127.0.0.1:8000/api/v1/me/learning-directory -H "Authorization: Bearer $TOKEN"
```

**Admin** — login without enrollment, browse learning directory:

```bash
ADMIN_TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@demo.school","password":"demo1234"}' | python -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
curl http://127.0.0.1:8000/api/v1/me/learning-directory -H "Authorization: Bearer $ADMIN_TOKEN"
```

**Quick demo** — bootstrap enrollments and progress in development:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/me/demo/bootstrap \
  -H "Authorization: Bearer $TOKEN"
```

Legacy flat list (prefer learning-directory): `GET /api/v1/materials`.

```bash
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

## Documentation

- [Documentation hub](docs/README.md) — vision, map, implementation matrix
- [Architecture](docs/architecture/README.md) — diagrams and HTML overview
- [Design specs](docs/design/README.md) — component contracts and data model
- [Backend README](backend/README.md) — API modules and access rules

# Education Platform

- Use `uv` for all Python commands from `backend/`; do not add `requirements.txt`.
- Keep HTTP routes thin. Place business logic in module services.
- Treat `docs/curriculum/` markdown as the approved curriculum source for seeding the SQLite
  materials/quiz tables. Student-facing quiz endpoints must not expose answer keys.
- Auth uses JWT access/refresh tokens; do not invent access grants beyond roles and enrollments.
- Student material/quiz/attempt access requires active Grade and Grade–Subject enrollments.
- Administrators may read institution learning-directory without student enrollments.
- Teacher role exists in schema; no teacher backend module yet — frontend uses fixtures.
- Read [`docs/README.md`](docs/README.md) for vision and implementation status before large features.
- Add or update tests for every behavior change. Before finishing, run Ruff format/check, mypy, and
  pytest from `backend/` (coverage gate is 80%).
- SQLite/Alembic schema lives under `backend/` (POC uses a local `education.db` file). Materials
  API reads published rows from SQLite after seed. Do not introduce MinIO until a feature needs
  blob storage.

## Cursor Cloud specific instructions

### Services (POC core)

| Service | Command | Notes |
| --- | --- | --- |
| Backend API | From `backend/`: `uv run uvicorn education_platform.main:app --reload --host 127.0.0.1 --port 8000` | SQLite file `backend/education.db`. After checkout, run `uv run alembic upgrade head` once per fresh DB. API auto-seeds curriculum from `docs/curriculum/` when no topics exist. |
| Frontend | From `frontend/`: `npm run dev` | Needs `frontend/.env` with `VITE_API_BASE_URL=http://127.0.0.1:8000` (copy from `.env.example`). Dev server on `:5173`. |
| Redis + ARQ worker | Optional | Only for PDF ingest / RAG (`docker compose up -d redis` + `uv run arq education_platform.workers.settings.WorkerSettings`). Not required for student quiz or admin materials browse. |

Standard quality commands: root [`README.md`](README.md) and [`backend/README.md`](backend/README.md). Backend gate from `backend/`: ruff format/check, mypy, pytest (80% coverage). Frontend: `npm test` (Vitest). Prefer `npm run dev` over `npm run build` for day-to-day work — `tsc --noEmit` in the production build currently fails on two pre-existing issues unrelated to runtime.

### Demo accounts

- Student: `student@demo.school` / `demo1234`
- Admin: `admin@demo.school` / `demo1234`

### Gotchas

- `uv` must be on `PATH` (`$HOME/.local/bin` after Astral install). All Python work uses `uv` from `backend/`.
- Do not start Redis/Docker unless exercising ingest; nested Docker is not set up by default in this Cloud Agent image.
- Pre-commit hooks live in `.pre-commit-config.yaml` (ruff on `backend/`); optional for agents, required quality gate is still the backend commands above.

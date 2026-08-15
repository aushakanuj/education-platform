# Education Platform

- Use `uv` for all Python commands from `backend/`; do not add `requirements.txt`.
- Keep HTTP routes thin. Place business logic in module services.
- Treat `docs/curriculum/` markdown as the approved curriculum source for seeding the Postgres
  materials/quiz tables. Student-facing quiz endpoints must not expose answer keys.
- Auth uses JWT access/refresh tokens; do not invent access grants beyond roles and enrollments.
- Student material/quiz/attempt access requires active Grade and Grade–Subject enrollments.
- Administrators may read institution learning-directory without student enrollments.
- Teacher role exists in schema; no teacher backend module yet — frontend uses fixtures.
- Read [`docs/README.md`](docs/README.md) for vision and implementation status before large features.
- Add or update tests for every behavior change. Before finishing, run Ruff format/check, mypy, and
  pytest from `backend/` (coverage gate is 80%).
- Postgres + pgvector (Compose) and Alembic schema live under `backend/`. Materials API reads
  published rows from Postgres after seed. PDF ingest is a Postgres `ingest_jobs` claim worker
  (`uv run python -m education_platform.workers`); keep local `UPLOAD_DIR` for PDF blobs; do not
  introduce MinIO until a feature needs shared object storage.

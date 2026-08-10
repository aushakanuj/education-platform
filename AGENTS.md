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

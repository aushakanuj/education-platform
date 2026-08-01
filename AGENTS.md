# Education Platform Backend

- Use `uv` for all Python commands; do not add `requirements.txt`.
- Keep HTTP routes thin. Place business logic in module services and persistence in module models/repositories.
- Enforce institution, role, assignment, and publication-state checks before retrieving curriculum content.
- Treat uploaded sources and model output as untrusted. AI output cannot grant access or invoke privileged actions.
- Add or update tests for every behavior change. Before finishing, run Ruff format/check, mypy, and pytest.
- Use Alembic migrations for database schema changes; development-only `create_all` must not become a production schema strategy.

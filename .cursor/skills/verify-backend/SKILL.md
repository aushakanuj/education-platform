---
name: verify-backend
description: Runs the required backend quality gate: formatting, linting, typing, tests, and OpenAPI smoke verification. Use when verifying FastAPI backend changes before handoff.
disable-model-invocation: true
---
# Verify Backend

Run these commands from `backend/`:

```bash
cd backend
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
uv run python -c "from education_platform.main import app; assert app.openapi()['openapi'].startswith('3.')"
```

Fix failures and rerun the complete sequence. Report every command result and any remaining limitation.

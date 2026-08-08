#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

log() {
  echo "==> $*"
}

if ! command -v uv >/dev/null 2>&1; then
  log "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

log "Installing Python 3.12..."
uv python install 3.12

log "Syncing dependencies..."
uv sync --all-groups --locked

log "Installing pre-commit hooks..."
uv run pre-commit install

if [[ ! -f .env ]]; then
  cp .env.example .env
  log "Created .env from .env.example; set JWT_SECRET_KEY before sharing the environment."
else
  log ".env already exists; leaving it unchanged."
fi

mkdir -p .local-storage

log "Applying database migrations (SQLite)..."
uv run alembic upgrade head

cat <<'EOF'

Setup complete.

Local development uses SQLite (education.db) by default.

Next steps:
  1. Review .env and set JWT_SECRET_KEY for non-local use
  2. Start the API: uv run uvicorn education_platform.main:app --reload
  3. Open API docs: http://127.0.0.1:8000/docs

Optional PostgreSQL stack:
  docker compose up -d
  # then switch DATABASE_URL in .env to the PostgreSQL URL from .env.example

Quality checks:
  uv run ruff format --check .
  uv run ruff check .
  uv run mypy src
  uv run pytest

Design docs: docs/project-overview.html (open in a browser)
EOF

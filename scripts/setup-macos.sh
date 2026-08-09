#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
cd "$BACKEND_DIR"

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

log "Syncing backend dependencies..."
uv sync --all-groups

log "Installing pre-commit hooks..."
uv run pre-commit install --config ../.pre-commit-config.yaml || uv run pre-commit install

if [[ ! -f .env ]]; then
  cp .env.example .env
  log "Created backend/.env from .env.example."
else
  log "backend/.env already exists; leaving it unchanged."
fi

cat <<'EOF'

Setup complete.

Next steps:
  1. Apply schema: cd backend && uv run alembic upgrade head
  2. Seed materials: cd backend && uv run python -m education_platform.modules.materials.seed
  3. Start the API: cd backend && uv run uvicorn education_platform.main:app --reload
  4. Open API docs: http://127.0.0.1:8000/docs

Quality checks (from backend/):
  uv run ruff format --check .
  uv run ruff check .
  uv run mypy src
  uv run alembic upgrade head
  uv run pytest

Approved materials live in docs/materials/.
Schema browser: docs/design/relational-schema.html
EOF

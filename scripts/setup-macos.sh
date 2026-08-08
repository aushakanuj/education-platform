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

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  log "Starting Docker Compose services (PostgreSQL, Redis, MinIO)..."
  docker compose up -d

  log "Waiting for PostgreSQL..."
  ready=false
  for _ in $(seq 1 30); do
    if docker compose exec -T postgres pg_isready -U education -d education >/dev/null 2>&1; then
      ready=true
      break
    fi
    sleep 1
  done

  if [[ "$ready" == true ]]; then
    log "Applying database migrations..."
    uv run alembic upgrade head
  else
    log "PostgreSQL did not become ready in time."
    log "Check Docker Desktop, then run: uv run alembic upgrade head"
  fi
else
  log "Docker is unavailable; skipping Compose services and migrations."
  log "Install and start Docker Desktop, then run:"
  log "  docker compose up -d"
  log "  uv run alembic upgrade head"
fi

cat <<'EOF'

Setup complete.

Next steps:
  1. Review .env and set JWT_SECRET_KEY for non-local use
  2. Start the API: uv run uvicorn education_platform.main:app --reload
  3. Open API docs: http://127.0.0.1:8000/docs

Quality checks:
  uv run ruff format --check .
  uv run ruff check .
  uv run mypy src
  uv run pytest

Design docs: docs/project-overview.html (open in a browser)
EOF

#!/usr/bin/env bash
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

uv python install 3.12
uv sync --all-groups
uv run pre-commit install

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example; set JWT_SECRET_KEY before sharing the environment."
fi

echo "Setup complete. Run: uv run uvicorn education_platform.main:app --reload"

$ErrorActionPreference = "Stop"

$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RootDir

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message"
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Step "Installing uv..."
    irm https://astral.sh/uv/install.ps1 | iex
    $env:Path = "$HOME\.local\bin;$env:Path"
}

Write-Step "Installing Python 3.12..."
uv python install 3.12

Write-Step "Syncing dependencies..."
uv sync --all-groups --locked

Write-Step "Installing pre-commit hooks..."
uv run pre-commit install

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Step "Created .env from .env.example; set JWT_SECRET_KEY before sharing the environment."
} else {
    Write-Step ".env already exists; leaving it unchanged."
}

New-Item -ItemType Directory -Force -Path ".local-storage" | Out-Null

Write-Step "Applying database migrations (SQLite)..."
uv run alembic upgrade head

Write-Host @"

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
"@

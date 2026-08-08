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

$dockerAvailable = $false
if (Get-Command docker -ErrorAction SilentlyContinue) {
    docker info *> $null
    if ($LASTEXITCODE -eq 0) {
        $dockerAvailable = $true
    }
}

if ($dockerAvailable) {
    Write-Step "Starting Docker Compose services (PostgreSQL, Redis, MinIO)..."
    docker compose up -d

    Write-Step "Waiting for PostgreSQL..."
    $ready = $false
    for ($i = 1; $i -le 30; $i++) {
        docker compose exec -T postgres pg_isready -U education -d education *> $null
        if ($LASTEXITCODE -eq 0) {
            $ready = $true
            break
        }
        Start-Sleep -Seconds 1
    }

    if ($ready) {
        Write-Step "Applying database migrations..."
        uv run alembic upgrade head
    } else {
        Write-Step "PostgreSQL did not become ready in time."
        Write-Step "Check Docker Desktop, then run: uv run alembic upgrade head"
    }
} else {
    Write-Step "Docker is unavailable; skipping Compose services and migrations."
    Write-Step "Install and start Docker Desktop, then run:"
    Write-Step "  docker compose up -d"
    Write-Step "  uv run alembic upgrade head"
}

Write-Host @"

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
"@

$ErrorActionPreference = "Stop"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    irm https://astral.sh/uv/install.ps1 | iex
    $env:Path = "$HOME\.local\bin;$env:Path"
}

uv python install 3.12
uv sync --all-groups
uv run pre-commit install

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example; set JWT_SECRET_KEY before sharing the environment."
}

Write-Host "Setup complete. Run: uv run uvicorn education_platform.main:app --reload"

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/src/education_platform/core/config.py → backend/ is parents[3], repo root parents[4]
_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_MATERIALS_DIR = _REPO_ROOT / "docs" / "materials"
_DEFAULT_DATABASE_URL = f"sqlite+aiosqlite:///{_BACKEND_ROOT / 'education.db'}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Education Platform"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    materials_dir: Path = _DEFAULT_MATERIALS_DIR
    database_url: str = _DEFAULT_DATABASE_URL
    jwt_secret: str = "dev-only-change-me-use-32bytes-min!!"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60
    refresh_token_days: int = 14
    mastery_pass_percent: float = 70.0


@lru_cache
def get_settings() -> Settings:
    return Settings()

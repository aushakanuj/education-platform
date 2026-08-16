from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/src/education_platform/core/config.py → backend/ is parents[3], repo root parents[4]
_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_MATERIALS_DIR = _REPO_ROOT / "docs" / "curriculum"
_DEFAULT_DATABASE_URL = "postgresql+asyncpg://education:education@localhost:5432/education"
_DEFAULT_UPLOAD_DIR = _BACKEND_ROOT / "var" / "uploads"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Education Platform"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]
    materials_dir: Path = _DEFAULT_MATERIALS_DIR
    database_url: str = _DEFAULT_DATABASE_URL
    jwt_secret: str = "dev-only-change-me-use-32bytes-min!!"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60
    refresh_token_days: int = 14
    mastery_pass_percent: float = 70.0
    demo_student_email: str = "student@demo.school"
    demo_student_password: str = "demo1234"
    demo_admin_email: str = "admin@demo.school"
    demo_admin_password: str = "demo1234"
    upload_dir: Path = _DEFAULT_UPLOAD_DIR
    embedding_model_name: str = "all-MiniLM-L6-v2"
    max_upload_bytes: int = 20 * 1024 * 1024
    ingest_allowed_content_types: list[str] = ["application/pdf"]
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4o-mini"
    chat_context_limit_tokens: int = 20_000
    chat_retrieval_limit: int = 6

    # Attendance below this percentage of the term makes a student exam-ineligible.
    # Sourced from Attendance Policy v3 section 2.1; the early-warning engine reads it.
    attendance_eligibility_percent: float = 75.0

    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"

    @property
    def openrouter_configured(self) -> bool:
        return bool(self.openrouter_api_key and self.openrouter_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()

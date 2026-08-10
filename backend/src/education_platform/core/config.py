from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/src/education_platform/core/config.py → backend/ is parents[3], repo root parents[4]
_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_MATERIALS_DIR = _REPO_ROOT / "docs" / "curriculum"
_DEFAULT_DATABASE_URL = f"sqlite+aiosqlite:///{_BACKEND_ROOT / 'education.db'}"
_DEFAULT_UPLOAD_DIR = _BACKEND_ROOT / "var" / "uploads"
_DEFAULT_VECTOR_DB_PATH = _BACKEND_ROOT / "education_vectors.db"


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
    redis_url: str = "redis://localhost:6379/0"
    upload_dir: Path = _DEFAULT_UPLOAD_DIR
    vector_db_path: Path = _DEFAULT_VECTOR_DB_PATH
    embedding_model_name: str = "all-MiniLM-L6-v2"
    max_upload_bytes: int = 20 * 1024 * 1024
    ingest_allowed_content_types: list[str] = ["application/pdf"]

    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()

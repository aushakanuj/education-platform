from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Education Agentic Platform"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite+aiosqlite:///./education.db"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    jwt_secret_key: SecretStr = SecretStr("change-this-development-secret-before-deploying")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    max_upload_size_bytes: int = 25 * 1024 * 1024
    local_storage_path: str = ".local-storage"


@lru_cache
def get_settings() -> Settings:
    return Settings()

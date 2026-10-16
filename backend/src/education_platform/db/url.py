"""Convert DATABASE_URL between async (asyncpg) and sync (psycopg) dialects."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


def to_async_url(url: str) -> str:
    """Return a SQLAlchemy async URL (postgresql+asyncpg)."""
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql+psycopg://"):
        return url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def to_sync_url(url: str) -> str:
    """Return a SQLAlchemy sync URL (postgresql+psycopg) for Alembic/seed/workers."""
    if url.startswith("postgresql+psycopg://"):
        return url
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


def with_credentials(url: str, *, user: str, password: str) -> str:
    """Same scheme/host/port/database/query as `url`, with different login credentials.

    Used to point the text-to-SQL pipeline's connection at a separate, least-privilege
    DB role (see `db.session.get_text_to_sql_engine`) without a second `DATABASE_URL`
    that would need to be kept in sync by hand across dev/test/CI — it's derived from
    whichever host/port/database `DATABASE_URL` already resolves to in that environment.
    """
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{user}:{password}@{host}{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))

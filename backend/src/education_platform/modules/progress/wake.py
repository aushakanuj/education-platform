from __future__ import annotations

import asyncio
from enum import StrEnum
from typing import Protocol

import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from education_platform.core.config import get_settings
from education_platform.db.url import to_async_url
from education_platform.modules.progress.types import ProgressSubject, parse_subject_key

PROGRESS_CHANNEL = "education_progress"


class WakeResult(StrEnum):
    NOTIFIED = "notified"
    TIMED_OUT = "timed_out"


class WakeWaiter(Protocol):
    async def wait(self, subject: ProgressSubject, timeout: float) -> WakeResult: ...

    async def aclose(self) -> None: ...


def publish_wake(session: Session, *subjects: ProgressSubject) -> None:
    """SELECT pg_notify on the current transaction. Caller commits."""
    seen: set[str] = set()
    for subject in subjects:
        key = subject.key()
        if key in seen:
            continue
        seen.add(key)
        session.execute(
            text("SELECT pg_notify(:channel, :payload)"),
            {"channel": PROGRESS_CHANNEL, "payload": key},
        )


async def publish_wake_async(session: AsyncSession, *subjects: ProgressSubject) -> None:
    seen: set[str] = set()
    for subject in subjects:
        key = subject.key()
        if key in seen:
            continue
        seen.add(key)
        await session.execute(
            text("SELECT pg_notify(:channel, :payload)"),
            {"channel": PROGRESS_CHANNEL, "payload": key},
        )


def _asyncpg_dsn() -> str:
    url = to_async_url(get_settings().database_url)
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


class PostgresWakeWaiter:
    """Dedicated LISTEN connection for one SSE client. Not borrowed from the ORM pool."""

    def __init__(self) -> None:
        self._conn: asyncpg.Connection | None = None
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._listening = False

    async def wait(self, subject: ProgressSubject, timeout: float) -> WakeResult:
        if timeout <= 0:
            return WakeResult.TIMED_OUT
        await self._ensure_listen()
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return WakeResult.TIMED_OUT
            try:
                payload = await asyncio.wait_for(self._queue.get(), timeout=remaining)
            except TimeoutError:
                return WakeResult.TIMED_OUT
            parsed = parse_subject_key(payload)
            if parsed is not None and parsed.key() == subject.key():
                return WakeResult.NOTIFIED

    async def aclose(self) -> None:
        conn = self._conn
        self._conn = None
        self._listening = False
        if conn is not None and not conn.is_closed():
            await conn.close()

    async def _ensure_listen(self) -> None:
        if self._listening and self._conn is not None and not self._conn.is_closed():
            return
        self._conn = await asyncpg.connect(_asyncpg_dsn())
        await self._conn.add_listener(PROGRESS_CHANNEL, self._on_notify)
        self._listening = True

    def _on_notify(
        self,
        _conn: asyncpg.Connection,
        _pid: int,
        _channel: str,
        payload: str,
    ) -> None:
        self._queue.put_nowait(payload)

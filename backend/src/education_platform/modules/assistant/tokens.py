"""Token estimation helpers for context-window accounting."""

from __future__ import annotations

import tiktoken

from education_platform.core.config import get_settings


def estimate_tokens(text: str) -> int:
    """Estimate tokens for OpenRouter/OpenAI-compatible models."""
    if not text:
        return 0
    try:
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:  # noqa: BLE001 — fallback when tiktoken data unavailable
        return max(1, len(text) // 4)


def context_percent(used: int, limit: int | None = None) -> int:
    settings = get_settings()
    cap = limit if limit is not None else settings.chat_context_limit_tokens
    if cap <= 0:
        return 0
    return min(100, int(round((used / cap) * 100)))

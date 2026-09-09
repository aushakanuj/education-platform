"""Compatibility re-export — the client lives in ``education_platform.core.llm``."""

from education_platform.core.llm import (
    OpenRouterError,
    build_openrouter_client,
    chat_completion,
    chat_completion_json,
)

__all__ = [
    "OpenRouterError",
    "build_openrouter_client",
    "chat_completion",
    "chat_completion_json",
]

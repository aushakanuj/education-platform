"""OpenRouter chat completions client (OpenAI-compatible API)."""

from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from education_platform.core.config import Settings, get_settings


class OpenRouterError(RuntimeError):
    """Raised when OpenRouter is misconfigured or the call fails."""


def build_openrouter_client(settings: Settings | None = None) -> AsyncOpenAI:
    cfg = settings or get_settings()
    if not cfg.openrouter_configured:
        raise OpenRouterError(
            "OPENROUTER_API_KEY is not configured. Set it in backend/.env to enable chat."
        )
    return AsyncOpenAI(
        api_key=cfg.openrouter_api_key,
        base_url=cfg.openrouter_base_url,
        default_headers={
            "HTTP-Referer": "https://github.com/aushakanuj/education-platform",
            "X-Title": "Education Platform Policy Assistant",
        },
    )


async def chat_completion(
    messages: list[dict[str, str]],
    *,
    settings: Settings | None = None,
    temperature: float = 0.0,
    response_json: bool = False,
) -> str:
    cfg = settings or get_settings()
    client = build_openrouter_client(cfg)
    kwargs: dict[str, Any] = {
        "model": cfg.openrouter_model,
        "messages": messages,
        "temperature": temperature,
    }
    if response_json:
        kwargs["response_format"] = {"type": "json_object"}
    response = await client.chat.completions.create(**kwargs)
    content = response.choices[0].message.content
    if not content:
        raise OpenRouterError("OpenRouter returned an empty completion")
    return str(content)


async def chat_completion_json(
    messages: list[dict[str, str]],
    *,
    settings: Settings | None = None,
    temperature: float = 0.0,
) -> dict[str, Any]:
    raw = await chat_completion(
        messages,
        settings=settings,
        temperature=temperature,
        response_json=True,
    )
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise OpenRouterError("Expected a JSON object from OpenRouter")
    return data

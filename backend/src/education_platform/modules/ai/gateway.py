"""Provider-agnostic gateway to a language model.

Text-to-SQL, document answering and quiz generation all need a model. Rather than each
picking its own, they call `get_provider()` here, so the provider is chosen once in
configuration and can be swapped without touching feature code.

**The provider decision (task 0.3) is still open.** Until the team settles it, the default
is `echo` -- a deterministic stub that returns predictable text and calls nothing external.
That keeps the test suite free and offline, and it means feature work is not blocked on the
decision: build against this interface now, add the real provider in one file later.

To add a provider: implement `LLMProvider`, register it in `_PROVIDERS`, and set
`LLM_PROVIDER` in the environment. Nothing else changes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from education_platform.core.config import get_settings


class LLMError(RuntimeError):
    """Raised when a provider cannot produce a response."""


@dataclass(frozen=True, slots=True)
class LLMResponse:
    text: str
    provider: str
    model: str
    #: Populated by real providers; the stub reports zero so cost logging still works.
    prompt_tokens: int = 0
    completion_tokens: int = 0
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LLMResponse: ...


class EchoProvider:
    """Deterministic stub. Same input always gives the same output, and nothing leaves
    the machine -- so tests are free, offline and repeatable.

    It answers in a shape each caller can recognise, which is enough to build and test the
    plumbing of text-to-SQL, document answering and quiz generation before a real provider
    is chosen.
    """

    name = "echo"

    def __init__(self, model: str = "echo-1") -> None:
        self.model = model

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LLMResponse:
        digest = hashlib.sha256(f"{system or ''}\n{prompt}".encode()).hexdigest()[:12]
        lowered = prompt.lower()

        if "sql" in lowered or "select" in lowered:
            text = "SELECT 1 AS placeholder /* echo provider: no model configured */"
        elif "json" in lowered:
            text = json.dumps({"echo": True, "digest": digest})
        else:
            text = f"[echo:{digest}] no language model is configured for this environment"

        return LLMResponse(
            text=text,
            provider=self.name,
            model=self.model,
            meta={"digest": digest, "stub": True},
        )


#: Register real providers here once task 0.3 is decided.
_PROVIDERS: dict[str, type] = {"echo": EchoProvider}

_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    """Return the configured provider, built once and reused."""
    global _provider
    if _provider is None:
        settings = get_settings()
        name = (settings.llm_provider or "echo").lower()
        factory = _PROVIDERS.get(name)
        if factory is None:
            raise LLMError(
                f"Unknown LLM provider {name!r}. Known providers: {sorted(_PROVIDERS)}. "
                "Add it to _PROVIDERS in modules/ai/gateway.py."
            )
        _provider = factory(model=settings.llm_model) if settings.llm_model else factory()
    return _provider


def reset_provider() -> None:
    """Test helper: drop the cached provider so settings changes take effect."""
    global _provider
    _provider = None

"""Scalable tool registry for the grounded assistant."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from education_platform.api.deps import Principal

ToolHandler = Callable[..., Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {name}") from exc

    def list_specs(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def openai_tools(self) -> list[dict[str, Any]]:
        return [spec.openai_schema() for spec in self._tools.values()]

    async def invoke(
        self,
        name: str,
        *,
        principal: Principal,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        spec = self.get(name)
        return await spec.handler(principal=principal, **arguments)


_REGISTRY = ToolRegistry()


def get_tool_registry() -> ToolRegistry:
    # Import built-ins once so register side effects run.
    from education_platform.modules.assistant.tools import retrieve_chunks as _retrieve

    _ = _retrieve
    return _REGISTRY


def register_tool(spec: ToolSpec) -> ToolSpec:
    if spec.name not in _REGISTRY._tools:  # noqa: SLF001 — intentional idempotent register
        _REGISTRY.register(spec)
    return spec

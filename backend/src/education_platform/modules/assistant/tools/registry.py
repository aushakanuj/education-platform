"""Scalable tool registry for the grounded assistant."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from education_platform.api.deps import Principal

ToolHandler = Callable[..., Awaitable[dict[str, Any]]]


class ToolValidationError(ValueError):
    """Raised when tool arguments or results fail Pydantic validation."""


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    handler: ToolHandler
    args_model: type[BaseModel]
    result_model: type[BaseModel]
    parameters: dict[str, Any] | None = None

    def json_schema(self) -> dict[str, Any]:
        if self.parameters is not None:
            return self.parameters
        schema = self.args_model.model_json_schema()
        # OpenAI tools expect a JSON Schema object without the title wrapper noise.
        schema.pop("title", None)
        return schema

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.json_schema(),
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
        try:
            validated_args = spec.args_model.model_validate(arguments)
        except ValidationError as exc:
            raise ToolValidationError(f"Invalid arguments for tool '{name}': {exc}") from exc

        raw = await spec.handler(principal=principal, **validated_args.model_dump())
        try:
            validated_result = spec.result_model.model_validate(raw)
        except ValidationError as exc:
            raise ToolValidationError(f"Invalid result from tool '{name}': {exc}") from exc
        return validated_result.model_dump(mode="python")


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

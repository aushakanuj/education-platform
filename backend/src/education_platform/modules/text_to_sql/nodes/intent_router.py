"""Routes approved in-domain questions to governed YAML templates or free-form SQL."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from education_platform.core.config import get_settings
from education_platform.modules.assistant.openrouter import OpenRouterError, chat_completion_json
from education_platform.modules.text_to_sql.state import TextToSQLState

_TEMPLATE_FILE: Final[str] = "intent_templates.yaml"
_TEXT_TO_SQL_ROOT = Path(__file__).resolve().parents[1]


class _RouterDecision(BaseModel):
    model_config = ConfigDict(extra="ignore")

    intent: str | None = None
    confidence: float = 0.0
    parameters: dict[str, Any] = Field(default_factory=dict)
    operation: str | None = None
    ambiguous: bool = False
    boundary_conflict: bool = False


@lru_cache(maxsize=1)
def _load_catalog() -> dict[str, Any]:
    path = _TEXT_TO_SQL_ROOT / "config" / _TEMPLATE_FILE
    with path.open(encoding="utf-8") as stream:
        catalog = yaml.safe_load(stream)
    if not isinstance(catalog, dict) or not isinstance(catalog.get("templates"), list):
        raise ValueError(f"invalid intent-router catalogue: {path}")
    return catalog


def _router_context(catalog: dict[str, Any]) -> str:
    config = catalog.get("intent_router", {})
    templates = []
    for template in catalog["templates"]:
        templates.append(
            {
                "name": template.get("name"),
                "description": template.get("description"),
                "parameters": template.get("parameters", {}),
                "requires_signoff": template.get("requires_signoff", False),
                "router": template.get("router", {}),
            }
        )
    return json.dumps({"intent_router": config, "templates": templates}, ensure_ascii=True)


def _normalize_parameters(
    parameters: dict[str, Any], catalog: dict[str, Any]
) -> dict[str, Any]:
    normalized = dict(parameters)
    subject_rules = catalog.get("intent_router", {}).get("normalization", {}).get("subject", {})
    aliases = subject_rules.get("aliases", {})
    if isinstance(aliases, dict) and normalized.get("subject") in aliases:
        normalized["subject"] = aliases[normalized["subject"]]
    return normalized


def _valid_parameters(template: dict[str, Any], parameters: dict[str, Any]) -> bool:
    definitions = template.get("parameters", {})
    router = template.get("router", {})
    for name in router.get("required_parameters", []):
        if name not in parameters or parameters[name] in (None, ""):
            return False
    for name, definition in definitions.items():
        if name not in parameters:
            if definition.get("required", False):
                return False
            if "default" in definition:
                parameters[name] = definition["default"]
            continue
        value = parameters[name]
        if definition.get("type") == "enum" and value not in definition.get("values", []):
            return False
        if definition.get("type") in {"number", "integer"}:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return False
            if definition.get("type") == "integer" and not isinstance(value, int):
                return False
            if "min" in definition and value < definition["min"]:
                return False
            if "max" in definition and value > definition["max"]:
                return False
        if "pattern" in definition and (
            not isinstance(value, str) or re.fullmatch(definition["pattern"], value) is None
        ):
            return False
    return True


def _select_template(
    decision: _RouterDecision, catalog: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    routing_policy = catalog.get("intent_router", {}).get("routing_policy", {})
    threshold = routing_policy.get("template_route_min_confidence", 0.90)
    if not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
        return None
    if not 0 <= decision.confidence <= 1:
        return None
    if decision.confidence < threshold or decision.intent is None:
        return None
    if decision.ambiguous or decision.boundary_conflict:
        return None
    for template in catalog["templates"]:
        if template.get("name") != decision.intent:
            continue
        router = template.get("router", {})
        if template.get("requires_signoff") or router.get("requires_approved_policy"):
            return None
        if decision.operation not in router.get("supported_operations", []):
            return None
        parameters = _normalize_parameters(decision.parameters, catalog)
        if not _valid_parameters(template, parameters):
            return None
        return template, parameters
    return None


def _free_form(state: TextToSQLState, decision: _RouterDecision | None = None) -> TextToSQLState:
    return {
        **state,
        "intent_route": "free_form",
        "intent": decision.intent if decision else None,
        "intent_confidence": decision.confidence if decision else 0.0,
        "intent_parameters": decision.parameters if decision else {},
        "query_source": None,
    }


async def intent_router(state: TextToSQLState) -> TextToSQLState:
    try:
        catalog = _load_catalog()
        settings = get_settings()
        if not settings.openrouter_configured:
            return _free_form(state)
        data = await chat_completion_json(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a conservative intent classifier. Use only the governed "
                        "catalog below. Return JSON with intent, confidence, parameters, "
                        "operation, ambiguous, and boundary_conflict. Choose null intent "
                        "when no template is an exact semantic match. Never classify a "
                        "template requiring signoff as usable.\n\n" + _router_context(catalog)
                    ),
                },
                {"role": "user", "content": state.get("question") or ""},
            ],
            settings=settings,
        )
        decision = _RouterDecision.model_validate(data)
    except (OSError, ValueError, OpenRouterError, json.JSONDecodeError, TypeError, ValidationError):
        return _free_form(state)

    selected = _select_template(decision, catalog)
    if selected is None:
        return _free_form(state, decision)

    template, parameters = selected
    shape = parameters.get("shape")
    sql_key = f"sql_{shape}" if shape else "sql"
    sql = template.get(sql_key)
    if not isinstance(sql, str) or not sql.strip():
        return _free_form(state, decision)
    return {
        **state,
        "intent_route": "template",
        "intent": template["name"],
        "intent_confidence": decision.confidence,
        "intent_parameters": parameters,
        "query_source": "template",
        "generated_sql": sql.strip(),
        "error": None,
    }


__all__ = ["intent_router"]

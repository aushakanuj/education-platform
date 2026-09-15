"""Pure outline math, DAG checks, and heuristic/LLM writers."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from decimal import ROUND_DOWN, Decimal
from uuid import UUID, uuid4

from education_platform.core.config import get_settings
from education_platform.modules.academics.models import Subtopic
from education_platform.modules.generation.adk import (
    OutlineRunner,
    OutlineRunRequest,
    live_outline_runner,
)
from education_platform.modules.generation.types import (
    HeadingCluster,
    OutlineNodeEdit,
    ProposedOutline,
    ProposedOutlineNode,
    ReviewStatus,
)

OutlineWriter = Callable[[Sequence[HeadingCluster]], ProposedOutline]

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_THREE = Decimal("3")


def largest_remainder(weights: Sequence[Decimal], n: int) -> tuple[int, ...]:
    """Integer quotas that sum to n. Hamilton / largest-remainder."""
    if n < 0:
        raise ValueError("n must be >= 0")
    if not weights:
        return ()
    values = [Decimal(weight) for weight in weights]
    total = sum(values, Decimal("0"))
    if total == 0:
        raise ValueError("all-zero weights")
    exact = [value / total * n for value in values]
    floors = [int(item.to_integral_value(rounding=ROUND_DOWN)) for item in exact]
    remainders = [item - floor for item, floor in zip(exact, floors, strict=True)]
    leftover = n - sum(floors)
    order = sorted(
        (index for index, value in enumerate(values) if value > 0),
        key=lambda index: (-remainders[index], index),
    )
    quotas = list(floors)
    for index in order[:leftover]:
        quotas[index] += 1
    return tuple(quotas)


def combined_weight(
    *,
    token_mass: int,
    prerequisite_score: Decimal,
    centrality: Decimal,
) -> Decimal:
    """Linear blend then left unnormalized. Equal coefficients on the three factors."""
    return (Decimal(token_mass) + prerequisite_score + centrality) / _THREE


def outline_from_headings(clusters: Sequence[HeadingCluster]) -> ProposedOutline:
    """Heuristic DAG: one node per heading, parent_key=None, prerequisite=0.5."""
    count = len(clusters)
    used_slugs: set[str] = set()
    nodes: list[ProposedOutlineNode] = []
    for index, cluster in enumerate(clusters):
        centrality = Decimal("1") if count == 1 else Decimal(count - index) / Decimal(count)
        slug = _unique_slug(_slugify(cluster.heading), used_slugs)
        used_slugs.add(slug)
        nodes.append(
            ProposedOutlineNode(
                key=f"h{index + 1}",
                parent_key=None,
                slug=slug,
                title=cluster.heading.strip() or f"Section {index + 1}",
                token_mass=cluster.token_mass,
                prerequisite_score=Decimal("0.5"),
                centrality=centrality,
                proposed_outcomes=(),
            )
        )
    return ProposedOutline(nodes=tuple(nodes))


def parse_proposed_outline(payload: dict[str, object]) -> ProposedOutline:
    """Boundary parse of LLM JSON. Invalid → ValueError, not a half-graph."""
    raw_nodes = payload.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise ValueError("outline JSON must include a non-empty nodes array")
    parsed: list[ProposedOutlineNode] = []
    keys: set[str] = set()
    for raw in raw_nodes:
        if not isinstance(raw, dict):
            raise ValueError("each outline node must be an object")
        node = _parse_proposed_node(raw)
        if node.key in keys:
            raise ValueError(f"duplicate outline key {node.key}")
        keys.add(node.key)
        parsed.append(node)
    keyset = keys
    for node in parsed:
        if node.parent_key is not None and node.parent_key not in keyset:
            raise ValueError(f"unknown parent_key {node.parent_key}")
        if node.parent_key == node.key:
            raise ValueError("outline node cannot parent itself")
    _assert_proposed_acyclic(parsed)
    return ProposedOutline(nodes=tuple(parsed))


def match_existing_subtopics(
    proposed: ProposedOutline,
    existing: Sequence[Subtopic],
) -> tuple[UUID | None, ...]:
    """Per node: slug match under the topic, else casefold name match, else None."""
    by_slug = {row.slug: row.id for row in existing}
    by_name = {row.name.casefold(): row.id for row in existing}
    matches: list[UUID | None] = []
    for node in proposed.nodes:
        slug_hit = by_slug.get(node.slug)
        if slug_hit is not None:
            matches.append(slug_hit)
            continue
        matches.append(by_name.get(node.title.casefold()))
    return tuple(matches)


def assert_dag(nodes: Sequence[OutlineNodeEdit]) -> None:
    """Reject unknown parent_id, cycles, duplicate ids. Called from patch_outline."""
    ids = [node.id for node in nodes]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate outline node ids")
    idset = set(ids)
    parent_of = {node.id: node.parent_id for node in nodes}
    for node in nodes:
        if node.parent_id is not None and node.parent_id not in idset:
            raise ValueError("unknown parent_id")
        if node.parent_id == node.id:
            raise ValueError("outline node cannot parent itself")
    for start in ids:
        seen: set[UUID] = set()
        current: UUID | None = start
        while current is not None:
            if current in seen:
                raise ValueError("outline DAG has a cycle")
            seen.add(current)
            current = parent_of.get(current)


def write_outline(
    clusters: Sequence[HeadingCluster],
    *,
    writer: OutlineWriter | None,
    runner: OutlineRunner | None = None,
    job_id: UUID | None = None,
) -> ProposedOutline:
    """If writer is None and OpenRouter is configured, default ADK outline graph."""
    if writer is not None:
        return writer(clusters)
    if runner is None and get_settings().openrouter_configured:
        runner = live_outline_runner()
    if runner is not None:
        return _outline_from_runner(clusters, runner, job_id=job_id)
    return outline_from_headings(clusters)


def _outline_from_runner(
    clusters: Sequence[HeadingCluster],
    runner: OutlineRunner,
    *,
    job_id: UUID | None,
) -> ProposedOutline:
    settings = get_settings()
    result = runner.generate(
        OutlineRunRequest(
            job_id=job_id or uuid4(),
            clusters=tuple(clusters),
            model=settings.adk_model,
            max_review_rounds=settings.adk_max_review_rounds,
        )
    )
    if result.review_status is not ReviewStatus.APPROVED:
        raise ValueError(result.reviewer_notes or "Outline critic rejected the draft.")
    return parse_proposed_outline(result.nodes_payload)


def _parse_proposed_node(raw: dict[str, object]) -> ProposedOutlineNode:
    key = _required_str(raw, "key")
    parent_raw = raw.get("parent_key")
    if parent_raw is None or parent_raw == "":
        parent_key = None
    elif isinstance(parent_raw, str):
        parent_key = parent_raw
    else:
        raise ValueError("parent_key must be a string or null")
    outcomes_raw = raw.get("proposed_outcomes") or []
    if not isinstance(outcomes_raw, list):
        raise ValueError("proposed_outcomes must be a list")
    outcomes: list[str] = []
    for item in outcomes_raw:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("proposed outcome statements must be non-empty strings")
        outcomes.append(item.strip())
    if len(outcomes) > 3:
        raise ValueError("at most 3 proposed outcomes per node")
    return ProposedOutlineNode(
        key=key,
        parent_key=parent_key,
        slug=_slugify(_optional_slug(raw) or _required_str(raw, "title")),
        title=_required_str(raw, "title"),
        token_mass=_required_int(raw, "token_mass"),
        prerequisite_score=_unit_score(raw, "prerequisite_score"),
        centrality=_unit_score(raw, "centrality"),
        proposed_outcomes=tuple(outcomes),
    )


def _assert_proposed_acyclic(nodes: Sequence[ProposedOutlineNode]) -> None:
    parent_of = {node.key: node.parent_key for node in nodes}
    for start in parent_of:
        seen: set[str] = set()
        current: str | None = start
        while current is not None:
            if current in seen:
                raise ValueError("outline DAG has a cycle")
            seen.add(current)
            current = parent_of.get(current)


def _required_str(raw: dict[str, object], field: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _optional_slug(raw: dict[str, object]) -> str:
    value = raw.get("slug")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return ""


def _required_int(raw: dict[str, object], field: str) -> int:
    value = raw.get(field)
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    if isinstance(value, int):
        number = value
    elif isinstance(value, float) and value.is_integer():
        number = int(value)
    else:
        raise ValueError(f"{field} must be an integer")
    if number < 0:
        raise ValueError(f"{field} must be >= 0")
    return number


def _unit_score(raw: dict[str, object], field: str) -> Decimal:
    value = raw.get(field)
    if isinstance(value, bool) or not isinstance(value, int | float | str | Decimal):
        raise ValueError(f"{field} must be a number")
    number = Decimal(str(value))
    if number < 0 or number > 1:
        raise ValueError(f"{field} must be between 0 and 1")
    return number


def _slugify(value: str) -> str:
    slug = _SLUG_RE.sub("-", value.strip().lower()).strip("-")
    return (slug[:100] or "section")[:100]


def _unique_slug(base: str, used: set[str]) -> str:
    if base not in used:
        return base
    index = 2
    while True:
        suffix = f"-{index}"
        candidate = f"{base[: 100 - len(suffix)]}{suffix}"
        if candidate not in used:
            return candidate
        index += 1

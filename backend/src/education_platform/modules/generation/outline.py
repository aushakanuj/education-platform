"""Pure outline math, DAG checks, and heuristic/LLM writers."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal, InvalidOperation
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

_logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_NOISE_HEADING = re.compile(r"^(?:ans\.?\b|page\s+no\.?\b|hint\s*:)", re.IGNORECASE)
_APPENDIX_HEADING = re.compile(r"^(?:ans\.?\b|page\s+no\.?\b)", re.IGNORECASE)
_HINT_HEADING = re.compile(r"^hint\s*:", re.IGNORECASE)
_HINT_LABEL = re.compile(r"^hint\s*:\s*", re.IGNORECASE)
_ANY_METHOD = re.compile(r"^method\s+\d+\s*:?$", re.IGNORECASE)
_KEPT_METHOD = re.compile(r"^method\s+[1-4]\s*:?$", re.IGNORECASE)
_POSSESSIVE_METHOD = re.compile(r".+['\u2019]s method\s*:?$", re.IGNORECASE)
_THREE = Decimal("3")
_NEUTRAL_SCORE = Decimal("0.5")
_ZERO = Decimal("0")
# Short headings fold into the next sibling. Method 1–4 stay even when they
# are under this floor. Fast Multiplications (about 40 tokens) stays its own lesson.
MIN_SECTION_TOKENS = 21
HEADING_PATH_SEPARATOR = " > "


@dataclass(frozen=True, slots=True)
class SourceSection:
    heading: str
    texts: tuple[str, ...]
    token_mass: int
    parent_heading: str | None = None


def preview_quotas(weights: Sequence[Decimal], target: int) -> tuple[int, ...]:
    """Question counts a review can show before the outline is accepted."""
    if target <= 0 or not weights:
        return tuple(0 for _ in weights)
    if sum(weights, Decimal("0")) == 0:
        return tuple(0 for _ in weights)
    return largest_remainder(tuple(Decimal(weight) for weight in weights), target)


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


def is_outline_noise_heading(heading: str) -> bool:
    """Answer keys, page numbers, and hint labels are not teaching sections."""
    return _NOISE_HEADING.match(heading.strip()) is not None


def source_sections(rows: Iterable[tuple[str | None, str, int]]) -> list[SourceSection]:
    """One run per heading path, in document order.

    "6.1 Some Properties > Increments in Products" is the leaf Increments in
    Products under the parent 6.1. A path with one part is a top-level section.
    A leaf that ends with ":" and is not Method 1–4 or a possessive method
    ("Tadang's method:") is body text and joins the previous sibling under the
    same parent. A Hint: chunk is not a section: the label is removed and the
    text joins the next sibling under the same parent, or the previous sibling
    when the next heading has a different parent. Everything from the first
    answer-key heading ("Ans.", "Page No.") onward is dropped.
    """
    sections: list[SourceSection] = []
    pending_hints: list[tuple[str | None, str, int]] = []
    for heading, text, tokens in rows:
        parts = [part.strip() for part in (heading or "").split(HEADING_PATH_SEPARATOR)]
        parts = [part for part in parts if part]
        if not parts:
            continue
        if any(_APPENDIX_HEADING.match(part) for part in parts):
            break
        leaf = parts[-1]
        parent = parts[0] if len(parts) > 1 else None
        if parent is not None and is_outline_noise_heading(parent):
            continue
        if _HINT_HEADING.match(leaf):
            pending_hints.append((parent, _strip_hint_label(text), tokens))
            continue
        if _is_colon_sentence(leaf):
            _absorb_colon_sentence(sections, leaf, text, tokens, parent)
            continue
        if is_outline_noise_heading(leaf):
            continue
        section = _section_with_pending_hints(
            SourceSection(leaf, (text,), tokens, parent),
            pending_hints,
            sections,
        )
        pending_hints.clear()
        previous = sections[-1] if sections else None
        if previous is not None and previous.heading == leaf and previous.parent_heading == parent:
            sections[-1] = _join_sections(previous, section)
        else:
            sections.append(section)
    _flush_hints(sections, pending_hints)
    return sections


def outline_clusters(
    sections: Sequence[SourceSection],
    *,
    min_tokens: int = MIN_SECTION_TOKENS,
) -> list[HeadingCluster]:
    """One cluster per heading, with numbered sections as parents of their leaves.

    A repeated leaf under the same parent joins its first run. A heading under
    ``min_tokens`` merges into the next sibling under that parent, or into the
    previous sibling when it is the last one. Method 1–4 stay even when they
    are shorter than ``min_tokens``. A numbered section that has children is a
    container: its token mass stays 0 and any text of its own is kept only as
    a sample.
    """
    merged = _merge_tiny_siblings(_collapse_repeated_leaves(sections), min_tokens)
    parents = {section.parent_heading for section in merged if section.parent_heading}
    exclusive = {
        section.heading: section
        for section in merged
        if section.parent_heading is None and section.heading in parents
    }
    clusters: list[HeadingCluster] = []
    emitted_parents: set[str] = set()
    for section in merged:
        parent = section.parent_heading
        if parent:
            if parent not in emitted_parents:
                clusters.append(_container_cluster(parent, exclusive.get(parent)))
                emitted_parents.add(parent)
            clusters.append(_leaf_cluster(section))
            continue
        if section.heading in parents:
            if section.heading not in emitted_parents:
                clusters.append(_container_cluster(section.heading, section))
                emitted_parents.add(section.heading)
            continue
        clusters.append(_leaf_cluster(section))
    return clusters


def _collapse_repeated_leaves(sections: Sequence[SourceSection]) -> list[SourceSection]:
    order: list[tuple[str | None, str]] = []
    by_key: dict[tuple[str | None, str], SourceSection] = {}
    for section in sections:
        key = (section.parent_heading, section.heading)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = section
            order.append(key)
        else:
            by_key[key] = _join_sections(existing, section)
    return [by_key[key] for key in order]


def _merge_tiny_siblings(sections: Sequence[SourceSection], min_tokens: int) -> list[SourceSection]:
    merged: list[SourceSection] = []
    pending: SourceSection | None = None
    for section in sections:
        if pending is not None and pending.parent_heading != section.parent_heading:
            _flush_tiny(merged, pending)
            pending = None
        if _folds_away(section, min_tokens, len(sections)):
            pending = section if pending is None else _join_sections(pending, section)
            continue
        if pending is not None:
            section = SourceSection(
                heading=section.heading,
                texts=pending.texts + section.texts,
                token_mass=pending.token_mass + section.token_mass,
                parent_heading=section.parent_heading,
            )
            pending = None
        merged.append(section)
    if pending is not None:
        _flush_tiny(merged, pending)
    return merged


def _folds_away(section: SourceSection, min_tokens: int, section_count: int) -> bool:
    if section_count <= 1 or section.token_mass >= min_tokens:
        return False
    return _KEPT_METHOD.match(section.heading.strip()) is None


def _is_colon_sentence(heading: str) -> bool:
    text = heading.strip()
    if not text.endswith(":"):
        return False
    if _ANY_METHOD.match(text) is not None:
        return False
    return _POSSESSIVE_METHOD.match(text) is None


def _strip_hint_label(text: str) -> str:
    return _HINT_LABEL.sub("", text.strip(), count=1).strip()


def _colon_sentence_texts(heading: str, text: str) -> tuple[str, ...]:
    sentence = heading.strip()
    body = text.strip()
    if body and sentence and sentence not in body:
        return (sentence, body)
    if body:
        return (body,)
    if sentence:
        return (sentence,)
    return ()


def _index_of_previous_sibling(sections: Sequence[SourceSection], parent: str | None) -> int | None:
    for index in range(len(sections) - 1, -1, -1):
        if sections[index].parent_heading == parent:
            return index
    return None


def _absorb_colon_sentence(
    sections: list[SourceSection],
    heading: str,
    text: str,
    tokens: int,
    parent: str | None,
) -> None:
    incoming = SourceSection(heading, _colon_sentence_texts(heading, text), tokens, parent)
    index = _index_of_previous_sibling(sections, parent)
    if index is None:
        sections.append(incoming)
        return
    sections[index] = _join_sections(sections[index], incoming)


def _section_with_pending_hints(
    section: SourceSection,
    pending: Sequence[tuple[str | None, str, int]],
    sections: list[SourceSection],
) -> SourceSection:
    matched_texts: list[str] = []
    matched_tokens = 0
    for hint_parent, hint_text, hint_tokens in pending:
        if hint_parent == section.parent_heading:
            if hint_text:
                matched_texts.append(hint_text)
            matched_tokens += hint_tokens
            continue
        _attach_hint(sections, hint_parent, hint_text, hint_tokens)
    if matched_tokens == 0 and not matched_texts:
        return section
    return SourceSection(
        heading=section.heading,
        texts=tuple(matched_texts) + section.texts,
        token_mass=section.token_mass + matched_tokens,
        parent_heading=section.parent_heading,
    )


def _flush_hints(
    sections: list[SourceSection], pending: Sequence[tuple[str | None, str, int]]
) -> None:
    for hint_parent, hint_text, hint_tokens in pending:
        _attach_hint(sections, hint_parent, hint_text, hint_tokens)


def _attach_hint(sections: list[SourceSection], parent: str | None, text: str, tokens: int) -> None:
    index = _index_of_previous_sibling(sections, parent)
    if index is None:
        return
    extra = (text,) if text else ()
    current = sections[index]
    sections[index] = SourceSection(
        heading=current.heading,
        texts=current.texts + extra,
        token_mass=current.token_mass + tokens,
        parent_heading=current.parent_heading,
    )


def _flush_tiny(merged: list[SourceSection], pending: SourceSection) -> None:
    if merged and merged[-1].parent_heading == pending.parent_heading:
        merged[-1] = _join_sections(merged[-1], pending)
    else:
        merged.append(pending)


def _container_cluster(heading: str, exclusive: SourceSection | None) -> HeadingCluster:
    samples = () if exclusive is None else tuple(text[:400] for text in exclusive.texts[:3])
    return HeadingCluster(heading=heading, token_mass=0, sample_texts=samples, parent_heading=None)


def _leaf_cluster(section: SourceSection) -> HeadingCluster:
    return HeadingCluster(
        heading=section.heading,
        token_mass=section.token_mass,
        sample_texts=tuple(text[:400] for text in section.texts[:3]),
        parent_heading=section.parent_heading,
    )


def _join_sections(first: SourceSection, second: SourceSection) -> SourceSection:
    return SourceSection(
        heading=first.heading,
        texts=first.texts + second.texts,
        token_mass=first.token_mass + second.token_mass,
        parent_heading=first.parent_heading,
    )


def ground_outline(
    proposed: ProposedOutline,
    clusters: Sequence[HeadingCluster],
) -> ProposedOutline:
    """Rebuild the outline from source clusters and keep matching model outcomes.

    Order, parents, and token masses come from the clusters. A numbered section
    is a sibling of the other numbered sections; its subheadings are its children.
    A model parent that points at a sibling is ignored. Container nodes carry no
    quota weight. Proposed outcomes attach only when the title and the parent
    both match, compared casefold. A null parent matches a node with no parent.
    A title match with a different parent does not attach.
    """
    usable = [
        cluster
        for cluster in clusters
        if cluster.heading.strip() and not is_outline_noise_heading(cluster.heading)
    ]
    if not usable:
        return proposed
    return _outline_from_clusters(usable, _outcome_index(proposed.nodes))


def outline_from_headings(clusters: Sequence[HeadingCluster]) -> ProposedOutline:
    """One node per cluster. Children point at their numbered section."""
    usable = [
        cluster
        for cluster in clusters
        if cluster.heading.strip() and not is_outline_noise_heading(cluster.heading)
    ]
    return _outline_from_clusters(usable, {})


def _folded_parent(parent: str | None) -> str | None:
    if parent is None:
        return None
    folded = parent.strip().casefold()
    return folded or None


def _outcome_index(
    nodes: Sequence[ProposedOutlineNode],
) -> dict[tuple[str, str | None], tuple[str, ...]]:
    """Outcomes keyed by casefolded title and parent. Later duplicates win."""
    indexed: dict[tuple[str, str | None], tuple[str, ...]] = {}
    for node in nodes:
        indexed[(node.title.strip().casefold(), _folded_parent(node.parent_title))] = (
            node.proposed_outcomes
        )
    return indexed


def _outline_from_clusters(
    clusters: Sequence[HeadingCluster],
    outcomes: dict[tuple[str, str | None], tuple[str, ...]],
) -> ProposedOutline:
    parent_names = {
        cluster.parent_heading.casefold()
        for cluster in clusters
        if cluster.parent_heading is not None
    }
    count = len(clusters)
    used_slugs: set[str] = set()
    parent_keys: dict[str, str] = {}
    nodes: list[ProposedOutlineNode] = []
    for index, cluster in enumerate(clusters):
        title = cluster.heading.strip() or f"Section {index + 1}"
        key = f"h{index + 1}"
        slug = _unique_slug(_slugify(title), used_slugs)
        used_slugs.add(slug)
        is_container = cluster.parent_heading is None and title.casefold() in parent_names
        parent_key = (
            None
            if cluster.parent_heading is None
            else parent_keys.get(cluster.parent_heading.casefold())
        )
        if cluster.parent_heading is None:
            parent_keys[title.casefold()] = key
        centrality = (
            _ZERO
            if is_container
            else (Decimal("1") if count == 1 else Decimal(count - index) / Decimal(count))
        )
        nodes.append(
            ProposedOutlineNode(
                key=key,
                parent_key=parent_key,
                slug=slug,
                title=title,
                token_mass=0 if is_container else cluster.token_mass,
                prerequisite_score=_ZERO if is_container else Decimal("0.5"),
                centrality=centrality,
                proposed_outcomes=outcomes.get(
                    (title.casefold(), _folded_parent(cluster.parent_heading)),
                    (),
                ),
                source_headings=(title,),
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
    for index, raw in enumerate(raw_nodes):
        if not isinstance(raw, dict):
            raise ValueError("each outline node must be an object")
        node = _parse_proposed_node(raw, fallback_key=f"n{index + 1}")
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
            model=settings.openrouter_model,
            max_review_rounds=settings.adk_max_review_rounds,
        )
    )
    # Grounding enforces source order and coverage; teachers review the draft next,
    # so neither an unapproved draft nor a malformed one fails the run.
    try:
        proposed = parse_proposed_outline(result.nodes_payload)
    except ValueError as exc:
        _logger.warning(
            "Outline draft is unparseable (%s, review %s); using source headings. Draft: %.1500s",
            exc,
            result.review_status.value,
            result.nodes_payload,
        )
        return outline_from_headings(
            [cluster for cluster in clusters if not is_outline_noise_heading(cluster.heading)]
        )
    if result.review_status is not ReviewStatus.APPROVED:
        _logger.warning(
            "Outline draft was not approved; keeping grounded draft: %s", result.reviewer_notes
        )
    return ground_outline(proposed, clusters)


def _parse_proposed_node(raw: dict[str, object], *, fallback_key: str) -> ProposedOutlineNode:
    title = _required_str(raw, "title")
    key = _optional_key(raw, fallback_key)
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
        slug=_slugify(_optional_slug(raw) or title),
        title=title,
        token_mass=_required_int(raw, "token_mass") if "token_mass" in raw else 0,
        prerequisite_score=_unit_score(raw, "prerequisite_score"),
        centrality=_unit_score(raw, "centrality"),
        proposed_outcomes=tuple(outcomes),
        source_headings=_source_headings(raw),
        parent_title=_optional_parent_title(raw),
    )


def _optional_key(raw: dict[str, object], fallback: str) -> str:
    if "key" not in raw or raw.get("key") in (None, ""):
        return fallback
    return _required_str(raw, "key")


def _optional_parent_title(raw: dict[str, object]) -> str | None:
    if "parent_title" not in raw:
        return None
    value = raw.get("parent_title")
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("parent_title must be a string or null")
    return value.strip() or None


def _source_headings(raw: dict[str, object]) -> tuple[str, ...]:
    value = raw.get("headings")
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("headings must be a list of strings")
    headings: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("headings must be non-empty strings")
        headings.append(item.strip())
    return tuple(headings)


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
    """Scores only weight quotas, so a missing or malformed one is neutral, not fatal."""
    value = raw.get(field)
    if isinstance(value, bool) or not isinstance(value, int | float | str | Decimal):
        return _NEUTRAL_SCORE
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation:
        return _NEUTRAL_SCORE
    if not number.is_finite():
        return _NEUTRAL_SCORE
    return min(Decimal("1"), max(Decimal("0"), number))


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

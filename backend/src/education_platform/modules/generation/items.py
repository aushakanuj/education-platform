"""Pure item-bank schemas, Bloom mix, and per-node writers."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

from education_platform.core.config import get_settings
from education_platform.modules.assessments.models import QuestionItemKind
from education_platform.modules.generation.adk import (
    BankItem,
    ItemNodeSpec,
    ItemsRunner,
    ItemsRunRequest,
    item_developer_instruction,
    item_kind_for_bloom,
    live_items_runner,
)
from education_platform.modules.generation.outline import largest_remainder
from education_platform.modules.generation.types import BloomLevel

OPTION_LABELS = ("A", "B", "C", "D")
_SLUG_RE = re.compile(r"[^a-z0-9]+")

_ITEMS_SYSTEM = item_developer_instruction()


@dataclass(frozen=True, slots=True)
class GeneratedItem:
    subtopic_id: UUID
    learning_outcome_ids: tuple[UUID, ...]
    prompt: str
    options: dict[str, str]
    correct_label: str
    correct_rationale: str
    distractor_rationales: dict[str, str]
    bloom: BloomLevel
    item_kind: QuestionItemKind = QuestionItemKind.PROBLEM
    source_method: str = ""
    misconception_labels: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OutlineNodeRef:
    id: UUID
    slug: str
    title: str
    sequence: int


@dataclass(frozen=True, slots=True)
class NodeItemRequest:
    subtopic_id: UUID
    learning_outcome_ids: tuple[UUID, ...]
    heading: str
    chunk_texts: tuple[str, ...]
    quota: int
    bloom: tuple[BloomLevel, ...]


ItemsWriter = Callable[[NodeItemRequest], Sequence[GeneratedItem]]


def item_scoring_rubric(
    bloom: BloomLevel, misconception_labels: Sequence[str] = ()
) -> dict[str, object]:
    return {
        "bloom": bloom.value,
        "misconceptions": [{"label": label} for label in misconception_labels],
    }


def bloom_from_rubric(raw: object) -> BloomLevel | None:
    if not isinstance(raw, dict):
        return None
    value = raw.get("bloom")
    if not isinstance(value, str):
        return None
    try:
        return BloomLevel(value.strip().lower())
    except ValueError:
        return None


def misconceptions_from_rubric(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, dict):
        return ()
    labels: list[str] = []
    value = raw.get("misconceptions")
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.strip():
                labels.append(item.strip())
            elif isinstance(item, dict):
                text = str(item.get("label") or item.get("id") or "").strip()
                if text:
                    labels.append(text)
    single = raw.get("misconception_id")
    if isinstance(single, str) and single.strip():
        labels.append(single.strip())
    return tuple(dict.fromkeys(labels))


def bloom_mix_for_quota(quota: int, *, heavy: bool) -> tuple[BloomLevel, ...]:
    """Lighter nodes lean Remember/Understand; heavier nodes lean Apply/Analyze."""
    if quota <= 0:
        return ()
    weights = (1, 2, 4, 3) if heavy else (4, 3, 2, 1)
    counts = largest_remainder(tuple(Decimal(weight) for weight in weights), quota)
    mix = (
        (BloomLevel.REMEMBER,) * counts[0]
        + (BloomLevel.UNDERSTAND,) * counts[1]
        + (BloomLevel.APPLY,) * counts[2]
        + (BloomLevel.ANALYZE,) * counts[3]
    )
    return mix


def node_is_heavy(quota: int, *, node_count: int, target: int) -> bool:
    """True when this node's share is above an equal split of the bank."""
    if node_count <= 0 or quota <= 0:
        return False
    return quota * node_count > target


def texts_for_nodes(
    nodes: Sequence[OutlineNodeRef],
    heading_groups: Sequence[tuple[str, tuple[str, ...]]],
) -> dict[UUID, tuple[str, ...]]:
    """Map each node to that heading's texts; neighbors only if the node has none.

    Never assigns every heading group to a single node unless there is only one group.
    """
    ordered = sorted(nodes, key=lambda node: node.sequence)
    assigned: dict[UUID, list[str]] = {node.id: [] for node in ordered}
    used_headings: set[str] = set()

    for heading, texts in heading_groups:
        match = _matching_node(ordered, heading)
        if match is None:
            continue
        assigned[match.id].extend(texts)
        used_headings.add(heading)

    leftover = [
        (heading, texts) for heading, texts in heading_groups if heading not in used_headings
    ]
    unmatched = [node for node in ordered if not assigned[node.id]]
    for node, (_heading, texts) in zip(unmatched, leftover, strict=False):
        assigned[node.id].extend(texts)

    for index, node in enumerate(ordered):
        if assigned[node.id]:
            continue
        neighbor_indexes = []
        if index > 0:
            neighbor_indexes.append(index - 1)
        if index + 1 < len(ordered):
            neighbor_indexes.append(index + 1)
        for neighbor_index in neighbor_indexes:
            assigned[node.id].extend(assigned[ordered[neighbor_index].id])
        if assigned[node.id] or not heading_groups:
            continue
        low = max(0, index - 1)
        high = min(len(heading_groups), index + 2)
        for _heading, texts in heading_groups[low:high]:
            assigned[node.id].extend(texts)

    return {node_id: tuple(texts) for node_id, texts in assigned.items()}


def parse_generated_items(
    payload: dict[str, object],
    request: NodeItemRequest,
) -> tuple[GeneratedItem, ...]:
    """Boundary parse of LLM JSON. Invalid items are dropped, not half-written."""
    raw_questions = payload.get("questions")
    if not isinstance(raw_questions, list):
        raise ValueError("items JSON must contain a questions array")
    items: list[GeneratedItem] = []
    for index, raw in enumerate(raw_questions):
        parsed = _parse_one_item(raw, request, index)
        if parsed is not None:
            items.append(parsed)
    return tuple(items)


def items_from_chunks(request: NodeItemRequest) -> tuple[GeneratedItem, ...]:
    """Heuristic fallback: one grounded MCQ per Bloom slot, never a whole-PDF dump."""
    texts = request.chunk_texts or (request.heading,)
    items: list[GeneratedItem] = []
    for index, bloom in enumerate(request.bloom):
        snippet = _snippet(texts[index % len(texts)])
        prompt = (
            f"Item {index + 1} ({bloom.value}) for {request.heading}: "
            f"which statement is grounded in this source excerpt: {snippet}?"
        )
        correct = f"A fact from the {request.heading} excerpt: {snippet}"
        items.append(
            GeneratedItem(
                subtopic_id=request.subtopic_id,
                learning_outcome_ids=request.learning_outcome_ids,
                prompt=prompt,
                options={
                    "A": correct,
                    "B": f"An unrelated claim that contradicts {request.heading}.",
                    "C": f"A common mix-up about {request.heading}.",
                    "D": f"A detail that the {request.heading} excerpt does not support.",
                },
                correct_label="A",
                correct_rationale=f"The excerpt for {request.heading} supports A.",
                distractor_rationales={
                    "B": "This contradicts the source excerpt.",
                    "C": "This is a common misconception, not the source fact.",
                    "D": "This is not stated in the excerpt.",
                },
                bloom=bloom,
                item_kind=item_kind_for_bloom(bloom),
                source_method=request.heading,
                misconception_labels=("common mix-up",),
            )
        )
    return tuple(items)


def write_items_for_node(
    request: NodeItemRequest,
    *,
    writer: ItemsWriter | None,
    runner: ItemsRunner | None = None,
    job_id: UUID | None = None,
    lesson_markdown: str = "",
) -> tuple[GeneratedItem, ...]:
    """If writer is None and OpenRouter is configured, default ADK items graph."""
    produced = write_items_for_nodes(
        (request,),
        writer=writer,
        runner=runner,
        job_id=job_id,
        lesson_markdown=lesson_markdown,
    )
    return produced[0] if produced else ()


def write_items_for_nodes(
    requests: Sequence[NodeItemRequest],
    *,
    writer: ItemsWriter | None,
    runner: ItemsRunner | None = None,
    job_id: UUID | None = None,
    lesson_markdown: str = "",
    apply_curriculum_mix: bool = False,
) -> tuple[tuple[GeneratedItem, ...], ...]:
    """Fan-out per outline node. Injected writers stay per-node; ADK uses ParallelAgent."""
    if not requests:
        return ()
    if writer is not None:
        return tuple(
            () if request.quota <= 0 else _coerce_to_quota(tuple(writer(request)), request)
            for request in requests
        )
    if runner is None and get_settings().openrouter_configured:
        runner = live_items_runner()
    if runner is not None:
        return _items_from_runner(
            requests,
            runner,
            job_id=job_id,
            lesson_markdown=lesson_markdown,
            apply_curriculum_mix=apply_curriculum_mix,
        )
    return tuple(items_from_chunks(request) if request.quota > 0 else () for request in requests)


def _items_from_runner(
    requests: Sequence[NodeItemRequest],
    runner: ItemsRunner,
    *,
    job_id: UUID | None,
    lesson_markdown: str,
    apply_curriculum_mix: bool,
) -> tuple[tuple[GeneratedItem, ...], ...]:
    settings = get_settings()
    specs = tuple(
        ItemNodeSpec(
            key=str(request.subtopic_id),
            heading=request.heading,
            chunk_texts=request.chunk_texts,
            quota=request.quota,
            bloom=tuple(level.value for level in request.bloom),
        )
        for request in requests
    )
    result = runner.generate(
        ItemsRunRequest(
            job_id=job_id or uuid4(),
            nodes=specs,
            lesson_markdown=lesson_markdown,
            model=settings.adk_model,
            max_review_rounds=settings.adk_max_review_rounds,
            apply_curriculum_mix=apply_curriculum_mix,
        )
    )
    if result.review_status.value != "approved" and not result.items:
        raise ValueError(result.reviewer_notes or "Item reviewer rejected the draft.")
    offset = 0
    grouped: list[tuple[GeneratedItem, ...]] = []
    for request in requests:
        chunk = result.items[offset : offset + request.quota]
        offset += request.quota
        produced = tuple(_generated_from_bank(item, request) for item in chunk)
        grouped.append(_coerce_to_quota(produced, request))
    return tuple(grouped)


def _generated_from_bank(item: BankItem, request: NodeItemRequest) -> GeneratedItem:
    return GeneratedItem(
        subtopic_id=request.subtopic_id,
        learning_outcome_ids=request.learning_outcome_ids,
        prompt=item.prompt,
        options=item.options,
        correct_label=item.correct_label,
        correct_rationale=item.explanation,
        distractor_rationales=item.distractor_rationales,
        bloom=item.bloom,
        item_kind=item.item_kind,
        source_method=item.source_method or request.heading,
        misconception_labels=item.misconception_labels,
    )


def _coerce_to_quota(
    produced: Sequence[GeneratedItem], request: NodeItemRequest
) -> tuple[GeneratedItem, ...]:
    aligned: list[GeneratedItem] = []
    for index, bloom in enumerate(request.bloom):
        if index < len(produced):
            item = produced[index]
            aligned.append(
                GeneratedItem(
                    subtopic_id=request.subtopic_id,
                    learning_outcome_ids=request.learning_outcome_ids or item.learning_outcome_ids,
                    prompt=item.prompt,
                    options=item.options,
                    correct_label=item.correct_label,
                    correct_rationale=item.correct_rationale,
                    distractor_rationales=item.distractor_rationales,
                    bloom=bloom,
                    item_kind=item.item_kind or item_kind_for_bloom(bloom),
                    source_method=item.source_method or request.heading,
                    misconception_labels=item.misconception_labels,
                )
            )
        else:
            aligned.extend(items_from_chunks(_replace_quota(request, start=index)))
            break
    return tuple(aligned[: request.quota])


def _replace_quota(request: NodeItemRequest, *, start: int) -> NodeItemRequest:
    remaining = request.bloom[start:]
    return NodeItemRequest(
        subtopic_id=request.subtopic_id,
        learning_outcome_ids=request.learning_outcome_ids,
        heading=request.heading,
        chunk_texts=request.chunk_texts,
        quota=len(remaining),
        bloom=remaining,
    )


def _parse_one_item(raw: object, request: NodeItemRequest, index: int) -> GeneratedItem | None:
    if not isinstance(raw, dict):
        return None
    prompt = str(raw.get("prompt") or "").strip()
    if len(prompt) < 10:
        return None
    options_raw = raw.get("options")
    if not isinstance(options_raw, dict):
        return None
    options = {str(key).strip().upper(): str(value).strip() for key, value in options_raw.items()}
    if set(options) != set(OPTION_LABELS) or any(not text for text in options.values()):
        return None
    correct = str(raw.get("correct") or raw.get("correct_label") or "").strip().upper()
    if correct not in options:
        return None
    rationale = str(raw.get("correct_rationale") or "").strip()
    if not rationale:
        return None
    distractors_raw = raw.get("distractor_rationales")
    if not isinstance(distractors_raw, dict):
        return None
    distractors = {
        str(key).strip().upper(): str(value).strip()
        for key, value in distractors_raw.items()
        if str(key).strip().upper() in OPTION_LABELS and str(key).strip().upper() != correct
    }
    missing = [label for label in OPTION_LABELS if label != correct and not distractors.get(label)]
    if missing:
        return None
    bloom = _parse_bloom(raw.get("bloom"), request.bloom, index)
    misconception = str(raw.get("misconception_id") or "").strip()
    labels = tuple(
        str(item).strip() for item in (raw.get("misconception_labels") or ()) if str(item).strip()
    )
    if misconception and misconception not in labels:
        labels = (*labels, misconception)
    return GeneratedItem(
        subtopic_id=request.subtopic_id,
        learning_outcome_ids=request.learning_outcome_ids,
        prompt=prompt,
        options=options,
        correct_label=correct,
        correct_rationale=rationale,
        distractor_rationales={
            label: distractors[label] for label in OPTION_LABELS if label != correct
        },
        bloom=bloom,
        item_kind=item_kind_for_bloom(bloom),
        source_method=str(raw.get("source_method") or request.heading).strip(),
        misconception_labels=labels,
    )


def _parse_bloom(raw: object, mix: tuple[BloomLevel, ...], index: int) -> BloomLevel:
    if isinstance(raw, str):
        try:
            return BloomLevel(raw.strip().lower())
        except ValueError:
            pass
    if 0 <= index < len(mix):
        return mix[index]
    return BloomLevel.REMEMBER


def _matching_node(nodes: Sequence[OutlineNodeRef], heading: str) -> OutlineNodeRef | None:
    heading_cf = heading.strip().casefold()
    heading_slug = _slugify(heading)
    for node in nodes:
        if node.title.strip().casefold() == heading_cf:
            return node
        if node.slug == heading_slug:
            return node
    return None


def _slugify(value: str) -> str:
    slug = _SLUG_RE.sub("-", value.strip().lower()).strip("-")
    return (slug[:100] or "section")[:100]


def _snippet(text: str) -> str:
    collapsed = " ".join(text.split())
    return collapsed[:120] if collapsed else "the source excerpt"

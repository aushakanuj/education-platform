"""Deterministic lesson gates run after the reviewer approves."""

from __future__ import annotations

import re

from education_platform.modules.generation.blueprint import MIN_CONCEPT_PROSE_CHARS
from education_platform.modules.materials.markdown_parser import parse_slides

_MERMAID_FENCE = re.compile(r"```mermaid[\s\S]*?```", re.IGNORECASE)
_BULLET_LINE = re.compile(r"^\s*[-*]\s+")
_H2_HEADING = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_META_TITLE = re.compile(
    r"objective|overview|summary|recap|mistake|agenda|warmup|warm-up",
    re.IGNORECASE,
)


def _prose_length(content: str) -> int:
    body = _MERMAID_FENCE.sub(" ", content)
    lines = [
        line.strip() for line in body.splitlines() if line.strip() and not _BULLET_LINE.match(line)
    ]
    return len(" ".join(lines))


def _lesson_blocks(markdown: str) -> list[tuple[str, str]]:
    slides = parse_slides(markdown)
    if slides:
        return [(slide.title, slide.content) for slide in slides]
    matches = list(_H2_HEADING.finditer(markdown))
    blocks: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        blocks.append((match.group(1).strip(), markdown[start:end].strip()))
    return blocks


def check_lesson_quality(markdown: str) -> str | None:
    blocks = _lesson_blocks(markdown)
    if not blocks:
        return "Lesson markdown has no parseable headings."
    if _MERMAID_FENCE.search(markdown) is None:
        return "Lesson must include at least one mermaid diagram fence."
    concept_slides = [block for block in blocks if _META_TITLE.search(block[0]) is None]
    if not concept_slides:
        return "Lesson must include at least one concept slide with teaching prose."
    short = [
        index + 1
        for index, (_title, content) in enumerate(concept_slides)
        if _prose_length(content) < MIN_CONCEPT_PROSE_CHARS
    ]
    if short:
        return (
            "Concept slides must teach in prose, not a thin bullet deck. "
            f"Slides {short} are shorter than {MIN_CONCEPT_PROSE_CHARS} characters of prose."
        )
    return None


def source_method_missing(lesson_markdown: str, source_method: str) -> bool:
    needle = source_method.strip().casefold()
    if not needle:
        return True
    return needle not in lesson_markdown.casefold()

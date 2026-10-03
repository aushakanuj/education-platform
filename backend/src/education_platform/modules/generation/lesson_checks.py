"""Deterministic lesson gates run after the reviewer approves."""

from __future__ import annotations

import re
from collections.abc import Sequence

from education_platform.modules.generation.blueprint import (
    MIN_CONCEPT_PROSE_CHARS,
    concept_prose_length,
    section_source_length_error,
)
from education_platform.modules.generation.lesson import (
    normalize_lesson_heading,
    parse_mermaid_diagram,
)
from education_platform.modules.materials.markdown_parser import parse_slides

_MERMAID_FENCE = re.compile(r"```mermaid\s*([\s\S]*?)```", re.IGNORECASE)
_H2_HEADING = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_META_TITLE = re.compile(
    r"objective|overview|summary|recap|mistake|agenda|warmup|warm-up",
    re.IGNORECASE,
)


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


def _sources_for_title(
    title: str, section_sources: Sequence[tuple[str, Sequence[str]]]
) -> Sequence[str] | None:
    key = normalize_lesson_heading(title)
    if not key:
        return None
    for heading, texts in section_sources:
        if normalize_lesson_heading(heading) == key:
            return texts
    return None


def check_lesson_quality(
    markdown: str,
    *,
    section_sources: Sequence[tuple[str, Sequence[str]]] | None = None,
) -> str | None:
    """Quality gate. Pass ``section_sources`` on the topic-lesson path so real text
    and untranscribed figures use different prose floors.
    """
    blocks = _lesson_blocks(markdown)
    if not blocks:
        return "Lesson markdown has no parseable headings."
    for body in _MERMAID_FENCE.findall(markdown):
        try:
            parse_mermaid_diagram(body)
        except ValueError as exc:
            return f"Mermaid diagram could not be parsed: {exc}"
    concept_slides = [block for block in blocks if _META_TITLE.search(block[0]) is None]
    if not concept_slides:
        return "Lesson must include at least one concept slide with teaching prose."
    if section_sources is None:
        short = [
            index + 1
            for index, (_title, content) in enumerate(concept_slides)
            if concept_prose_length(content) < MIN_CONCEPT_PROSE_CHARS
        ]
        if short:
            return (
                "Concept slides must teach in prose, not a thin bullet deck. "
                f"Slides {short} are shorter than {MIN_CONCEPT_PROSE_CHARS} characters of prose."
            )
        return None
    problems: list[str] = []
    for title, content in concept_slides:
        texts = _sources_for_title(title, section_sources)
        if texts is None:
            if concept_prose_length(content) < MIN_CONCEPT_PROSE_CHARS:
                problems.append(
                    f"{title} is shorter than {MIN_CONCEPT_PROSE_CHARS} characters of prose."
                )
            continue
        error = section_source_length_error(content, texts, heading=title)
        if error is not None:
            problems.append(error)
    if problems:
        return " ".join(problems)
    return None


_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "in",
    "on",
    "at",
    "to",
    "for",
    "with",
    "by",
    "of",
    "from",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "this",
    "that",
    "these",
    "those",
    "it",
}


def source_method_missing(lesson_markdown: str, source_method: str) -> bool:
    needle = source_method.strip().casefold()
    if not needle:
        return True
    haystack = lesson_markdown.casefold()
    if needle in haystack:
        return False
    needle_tokens = [w for w in _WORD_RE.findall(needle) if len(w) > 2 and w not in _STOPWORDS]
    if not needle_tokens:
        needle_tokens = _WORD_RE.findall(needle)
    if not needle_tokens:
        return True
    haystack_tokens = set(_WORD_RE.findall(haystack))
    matched = sum(1 for token in needle_tokens if token in haystack_tokens)
    overlap_ratio = matched / len(needle_tokens)
    return overlap_ratio < 0.6

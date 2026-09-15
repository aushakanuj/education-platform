"""Sequential section-wise topic lesson authoring. Never a one-shot PDF dump.

``write_topic_lesson`` still persists one markdown string (``draft_lesson_markdown``).
Internally it walks frozen outline nodes in sequence, then a thin stitch pass.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from uuid import UUID, uuid4

from education_platform.core.config import get_settings
from education_platform.modules.generation.adk import (
    LessonRunner,
    LessonRunRequest,
    LessonSectionSpec,
    instructional_designer_instruction,
    live_lesson_runner,
    stitch_agent_instruction,
)

_OVERFLOW_CHARS = 8000
_MERMAID_FENCE = re.compile(r"```mermaid\s*([\s\S]*?)```", re.IGNORECASE)
_MERMAID_START = re.compile(
    r"^(flowchart|graph|sequenceDiagram|classDiagram|stateDiagram(?:-v2)?|"
    r"erDiagram|journey|gantt|pie|mindmap)\b",
    re.IGNORECASE,
)

_SECTION_SYSTEM = instructional_designer_instruction(heading_style="section")
_STITCH_SYSTEM = stitch_agent_instruction()


class SectionPass(StrEnum):
    FULL = "full"
    IDEA = "idea"
    EXAMPLES = "examples"


@dataclass(frozen=True, slots=True)
class LessonSectionRequest:
    heading: str
    objectives: tuple[str, ...]
    chunk_texts: tuple[str, ...]
    grade_voice: str
    glossary: tuple[tuple[str, str], ...]
    prior_titles: tuple[str, ...]
    defined_terms: tuple[str, ...]
    prior_recap: str
    pass_kind: SectionPass = SectionPass.FULL


@dataclass(frozen=True, slots=True)
class LessonSection:
    heading: str
    markdown: str
    recap: str
    defined_terms: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StitchRequest:
    grade_voice: str
    sections: tuple[LessonSection, ...]


SectionWriter = Callable[[LessonSectionRequest], str]
StitchWriter = Callable[[StitchRequest], str]
TopicLessonWriter = SectionWriter


def carry_forward_brief(request: LessonSectionRequest) -> str:
    """What earlier sections already taught, which words are defined, what not to repeat."""
    if not request.prior_titles:
        return (
            "This is the first section. Define new terms as they appear. "
            "Do not assume earlier teaching."
        )
    terms = ", ".join(request.defined_terms) or "none yet"
    titles = "; ".join(request.prior_titles)
    recap = request.prior_recap.strip() or "See earlier recaps."
    return (
        f"Already taught: {titles}. Already defined: {terms}. "
        f"Do not repeat those definitions. Carry-forward recap: {recap}"
    )


def parse_mermaid_diagram(source: str) -> str:
    """Boundary parse of one mermaid body. Invalid → ValueError, not a half-diagram."""
    text = source.strip()
    if not text:
        raise ValueError("mermaid diagram is empty")
    first = text.splitlines()[0].strip()
    if _MERMAID_START.match(first) is None:
        raise ValueError("unrecognized mermaid diagram type")
    if text.count("[") != text.count("]"):
        raise ValueError("unbalanced mermaid brackets")
    if text.count("(") != text.count(")"):
        raise ValueError("unbalanced mermaid parentheses")
    return text


def assert_usable_mermaid(markdown: str) -> None:
    fences = _MERMAID_FENCE.findall(markdown)
    if not fences:
        raise ValueError("lesson section must include a mermaid fence")
    for body in fences:
        parse_mermaid_diagram(body)


def extract_recap(markdown: str, heading: str) -> str:
    match = re.search(
        r"\*\*Recap\.?\*\*\s*(.+?)(?:\n\s*\n|\Z)",
        markdown,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match is not None:
        return " ".join(match.group(1).split())[:400]
    return heading


def section_from_chunks(request: LessonSectionRequest) -> str:
    """Heuristic teach rewrite grounded in this node's excerpts only."""
    excerpt = _snippet(" ".join(request.chunk_texts), 400)
    label = _mermaid_label(request.heading)
    mermaid = (
        "```mermaid\n"
        f"flowchart TD\n"
        f'  idea["{label}"] --> why[Why it matters]\n'
        f"  why --> try[Try it]\n"
        "```"
    )
    idea_line = (
        f"In {request.grade_voice}, {request.heading} means this: {excerpt}"
        if request.pass_kind is not SectionPass.EXAMPLES
        else f"Keep the idea of {request.heading} and look at the source numbers."
    )
    example_line = (
        f"From the source for {request.heading}: {excerpt}"
        if request.pass_kind is not SectionPass.IDEA
        else f"Hold the definition of {request.heading}; examples come next."
    )
    prior = ", ".join(request.prior_titles) or "an unrelated idea"
    return (
        f"## {request.heading}\n\n"
        f"**The idea.** {idea_line}\n\n"
        f"**Why it matters.** You will use {request.heading} in later problems in this topic.\n\n"
        f"{mermaid}\n\n"
        f"**Worked example.** {example_line}\n\n"
        f"**Try it.** Using only {request.heading}, "
        f"answer a question about: {_snippet(excerpt, 80)}\n\n"
        f"**Common mistakes.** Do not mix this up with {prior}. Stay with the excerpt.\n\n"
        f"**Recap.** {request.heading}: {_snippet(excerpt, 120)}\n"
    )


def stitch_sections(request: StitchRequest) -> str:
    """2–3 sentence bridges and one topic recap. Does not rewrite the teaching."""
    if not request.sections:
        raise ValueError("cannot stitch an empty lesson")
    parts: list[str] = [f"# Lesson\n\n{request.grade_voice}"]
    titles = [section.heading for section in request.sections]
    for index, section in enumerate(request.sections):
        if index > 0:
            previous = titles[index - 1]
            parts.append(
                f"*Bridge.* You already learned {previous}. "
                f"Next we teach {section.heading} using the new excerpts, "
                f"without repeating the earlier definitions."
            )
        parts.append(section.markdown.strip())
    recap_bits = "; ".join(titles)
    parts.append(f"**Topic recap.** This lesson taught {recap_bits}.")
    return "\n\n".join(parts).strip() + "\n"


@dataclass(frozen=True, slots=True)
class WrittenTopicLesson:
    sections: tuple[LessonSection, ...]
    markdown: str


def write_topic_lesson(
    sections: Sequence[LessonSectionRequest],
    *,
    write_section: SectionWriter | None = None,
    write_stitch: StitchWriter | None = None,
    runner: LessonRunner | None = None,
    job_id: UUID | None = None,
) -> str:
    """Sequential section writers then stitch. One markdown string for the run.

    Do not pass every PDF chunk as a single section. The worker loops accepted
    outline nodes in ``sequence`` and supplies that heading's chunks (neighbors
    only when the node has none).
    """
    return write_topic_lesson_document(
        sections,
        write_section=write_section,
        write_stitch=write_stitch,
        runner=runner,
        job_id=job_id,
    ).markdown


def write_topic_lesson_document(
    sections: Sequence[LessonSectionRequest],
    *,
    write_section: SectionWriter | None = None,
    write_stitch: StitchWriter | None = None,
    runner: LessonRunner | None = None,
    job_id: UUID | None = None,
) -> WrittenTopicLesson:
    """Same sequential walk as ``write_topic_lesson``, plus the per-node sections."""
    if not sections:
        raise ValueError("cannot write a lesson with no sections")
    if write_section is None and write_stitch is None:
        if runner is None and get_settings().openrouter_configured:
            runner = live_lesson_runner()
        if runner is not None:
            return _lesson_from_runner(sections, runner, job_id=job_id)
    written: list[LessonSection] = []
    glossary = sections[0].glossary
    defined = sections[0].defined_terms
    prior_titles: tuple[str, ...] = ()
    prior_recap = ""
    for seed in sections:
        request = replace(
            seed,
            glossary=glossary,
            defined_terms=defined,
            prior_titles=prior_titles,
            prior_recap=prior_recap,
        )
        markdown = _write_section_passes(request, write_section)
        recap = extract_recap(markdown, request.heading)
        terms = _merge_terms(defined, request.heading)
        written.append(
            LessonSection(
                heading=request.heading,
                markdown=markdown,
                recap=recap,
                defined_terms=terms,
            )
        )
        glossary = _merge_glossary(glossary, request.heading, recap)
        defined = terms
        prior_titles = (*prior_titles, request.heading)
        prior_recap = recap
    stitch_request = StitchRequest(grade_voice=sections[0].grade_voice, sections=tuple(written))
    if write_stitch is not None:
        markdown = write_stitch(stitch_request)
    else:
        markdown = stitch_sections(stitch_request)
    return WrittenTopicLesson(sections=tuple(written), markdown=markdown)


def _lesson_from_runner(
    sections: Sequence[LessonSectionRequest],
    runner: LessonRunner,
    *,
    job_id: UUID | None,
) -> WrittenTopicLesson:
    expanded: list[LessonSectionRequest] = []
    for seed in sections:
        expanded.extend(_split_if_needed(seed))
    settings = get_settings()
    specs = tuple(
        LessonSectionSpec(
            heading=item.heading,
            objectives=item.objectives,
            chunk_texts=item.chunk_texts,
            grade_voice=item.grade_voice,
            glossary=item.glossary,
            prior_titles=item.prior_titles,
            defined_terms=item.defined_terms,
            prior_recap=item.prior_recap,
            pass_kind=item.pass_kind.value,
            heading_style="section",
        )
        for item in expanded
    )
    result = runner.generate(
        LessonRunRequest(
            job_id=job_id or uuid4(),
            sections=specs,
            model=settings.adk_model,
            max_review_rounds=settings.adk_max_review_rounds,
        )
    )
    if result.review_status.value != "approved" and not result.markdown.strip():
        raise ValueError(result.reviewer_notes or "Lesson pedagogy reviewer rejected the draft.")
    markdowns = list(result.sections_markdown) or [result.markdown]
    written: list[LessonSection] = []
    for index, request in enumerate(expanded):
        markdown = markdowns[index] if index < len(markdowns) else result.markdown
        assert_usable_mermaid(markdown)
        written.append(
            LessonSection(
                heading=request.heading,
                markdown=markdown,
                recap=extract_recap(markdown, request.heading),
                defined_terms=_merge_terms((), request.heading),
            )
        )
    stitched = result.markdown.strip() or stitch_sections(
        StitchRequest(grade_voice=sections[0].grade_voice, sections=tuple(written))
    )
    assert_usable_mermaid(stitched)
    return WrittenTopicLesson(sections=tuple(written), markdown=stitched)


def _write_section_passes(request: LessonSectionRequest, writer: SectionWriter | None) -> str:
    passes = _split_if_needed(request)
    parts = [_render_section(item, writer) for item in passes]
    return "\n\n".join(parts)


def _split_if_needed(request: LessonSectionRequest) -> tuple[LessonSectionRequest, ...]:
    total = sum(len(text) for text in request.chunk_texts)
    if (
        request.pass_kind is not SectionPass.FULL
        or total <= _OVERFLOW_CHARS
        or len(request.chunk_texts) < 2
    ):
        return (request,)
    mid = max(1, len(request.chunk_texts) // 2)
    idea = replace(
        request,
        chunk_texts=request.chunk_texts[:mid],
        pass_kind=SectionPass.IDEA,
    )
    examples = replace(
        request,
        chunk_texts=request.chunk_texts[mid:],
        pass_kind=SectionPass.EXAMPLES,
    )
    return (idea, examples)


def _render_section(request: LessonSectionRequest, writer: SectionWriter | None) -> str:
    markdown = _produce_section(request, writer)
    try:
        assert_usable_mermaid(markdown)
        return markdown
    except ValueError:
        markdown = _produce_section(request, writer)
        assert_usable_mermaid(markdown)
        return markdown


def _produce_section(request: LessonSectionRequest, writer: SectionWriter | None) -> str:
    if writer is not None:
        return writer(request)
    return section_from_chunks(request)


def _merge_glossary(
    glossary: tuple[tuple[str, str], ...], heading: str, recap: str
) -> tuple[tuple[str, str], ...]:
    key = heading.strip().casefold()
    if any(term.strip().casefold() == key for term, _definition in glossary):
        return glossary
    return (*glossary, (heading, recap[:200] or heading))


def _merge_terms(existing: tuple[str, ...], heading: str) -> tuple[str, ...]:
    if heading in existing:
        return existing
    return (*existing, heading)


def _snippet(text: str, limit: int) -> str:
    collapsed = " ".join(text.split())
    if not collapsed:
        return "the source excerpt"
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


def _mermaid_label(heading: str) -> str:
    cleaned = heading.replace('"', "'")
    return cleaned[:60] or "Idea"

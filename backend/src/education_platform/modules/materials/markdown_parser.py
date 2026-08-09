"""Parse approved curriculum markdown into structured lesson/quiz data."""

from __future__ import annotations

import re
from dataclasses import dataclass

_SLIDE_HEADING = re.compile(r"^## Slide (\d+)\s*[—\-]\s*(.+?)\s*$", re.MULTILINE)
_TITLE_HEADING = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_QUESTION_BLOCK = re.compile(r"(?ms)^(\d+)\.\s+(?:\*\*\[([^\]]+)\]\*\*\s*)?(.+?)(?=^\d+\.\s+|\Z)")
_OPTION_LINE = re.compile(r"^\s*([A-D])\)\s*(.+?)\s*$", re.MULTILINE)
_ANSWER_KEY_SPLIT = re.compile(r"(?mi)^##\s+Answer Key\s*$")
_ANSWER_LINE = re.compile(r"(?m)^(\d+)\.\s+\*\*([A-D]|True|False)\*\*(?:\s*[—\-]\s*(.+))?$")


@dataclass(frozen=True)
class ParsedSlide:
    number: int
    title: str
    content: str


@dataclass(frozen=True)
class ParsedOption:
    label: str
    text: str


@dataclass(frozen=True)
class ParsedQuestion:
    number: int
    difficulty: str | None
    prompt: str
    options: list[ParsedOption]
    correct_option_label: str | None
    explanation: str | None


@dataclass(frozen=True)
class ParsedLesson:
    title: str
    markdown: str
    slides: list[ParsedSlide]


@dataclass(frozen=True)
class ParsedQuiz:
    title: str
    questions: list[ParsedQuestion]


def title_from_markdown(markdown: str, fallback: str) -> str:
    match = _TITLE_HEADING.search(markdown)
    if match:
        return match.group(1).strip()
    return fallback.replace("_", " ").title()


def parse_slides(markdown: str) -> list[ParsedSlide]:
    matches = list(_SLIDE_HEADING.finditer(markdown))
    slides: list[ParsedSlide] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        slides.append(
            ParsedSlide(
                number=int(match.group(1)),
                title=match.group(2).strip(),
                content=markdown[start:end].strip(),
            )
        )
    return slides


def parse_lesson(markdown: str, topic_id: str) -> ParsedLesson:
    return ParsedLesson(
        title=title_from_markdown(markdown, topic_id),
        markdown=markdown,
        slides=parse_slides(markdown),
    )


def _strip_answer_key(markdown: str) -> str:
    parts = _ANSWER_KEY_SPLIT.split(markdown, maxsplit=1)
    return parts[0].rstrip()


def _parse_answer_key(answer_section: str) -> dict[int, tuple[str, str | None]]:
    answers: dict[int, tuple[str, str | None]] = {}
    for match in _ANSWER_LINE.finditer(answer_section):
        number = int(match.group(1))
        label = match.group(2).strip().upper()
        if label in {"TRUE", "FALSE"}:
            label = "A" if label == "TRUE" else "B"
        explanation = match.group(3).strip() if match.group(3) else None
        answers[number] = (label, explanation)
    return answers


def parse_quiz(markdown: str, topic_id: str) -> ParsedQuiz:
    if _ANSWER_KEY_SPLIT.search(markdown) is None:
        raise ValueError(f"Quiz for '{topic_id}' is missing an Answer Key section")

    parts = _ANSWER_KEY_SPLIT.split(markdown, maxsplit=1)
    body = parts[0]
    answer_section = parts[1] if len(parts) > 1 else ""
    answers = _parse_answer_key(answer_section)

    body_for_parse = re.sub(r"^#\s+.+?\n", "", _strip_answer_key(body), count=1).strip()
    body_for_parse = re.sub(
        r"(?mi)^##\s+Multiple-Choice Questions\s*$",
        "",
        body_for_parse,
        count=1,
    ).strip()

    questions: list[ParsedQuestion] = []
    for match in _QUESTION_BLOCK.finditer(body_for_parse):
        number = int(match.group(1))
        difficulty = match.group(2).strip() if match.group(2) else None
        block = match.group(3).strip()
        options = [
            ParsedOption(label=option.group(1), text=option.group(2).strip())
            for option in _OPTION_LINE.finditer(block)
        ]
        prompt = _OPTION_LINE.sub("", block).strip()
        prompt = re.sub(r"\n{2,}", "\n", prompt).strip()
        if not options:
            continue
        correct_label, explanation = answers.get(number, (None, None))
        questions.append(
            ParsedQuestion(
                number=number,
                difficulty=difficulty,
                prompt=prompt,
                options=options,
                correct_option_label=correct_label,
                explanation=explanation,
            )
        )

    if not questions:
        raise ValueError(f"Quiz for '{topic_id}' has no parseable multiple-choice questions")
    if any(question.correct_option_label is None for question in questions):
        missing = [q.number for q in questions if q.correct_option_label is None]
        raise ValueError(f"Quiz for '{topic_id}' missing answer-key entries for: {missing}")

    return ParsedQuiz(title=title_from_markdown(markdown, topic_id), questions=questions)

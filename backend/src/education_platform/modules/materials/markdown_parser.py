"""Parse approved curriculum markdown into structured lesson/quiz data."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SLIDE_HEADING = re.compile(r"^## Slide (\d+)\s*[—\-]\s*(.+?)\s*$", re.MULTILINE)
_TITLE_HEADING = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_QUESTION_BLOCK = re.compile(r"(?ms)^(\d+)\.\s+(?:\*\*\[([^\]]+)\]\*\*\s*)?(.+?)(?=^\d+\.\s+|\Z)")
_OPTION_LINE = re.compile(r"^\s*([A-D])\)\s*(.+?)\s*$", re.MULTILINE)
_ANSWER_KEY_SPLIT = re.compile(r"(?mi)^##\s+Answer Key\s*$")
_ANSWER_LINE = re.compile(r"(?m)^(\d+)\.\s+\*\*([A-D]|True|False)\*\*(?:\s*[—\-]\s*(.+))?$")

OptionLabel = Literal["A", "B", "C", "D"]


class ParsedSlide(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    number: int = Field(ge=1)
    title: str = Field(min_length=1)
    content: str


class ParsedOption(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    label: OptionLabel
    text: str = Field(min_length=1)


class AnswerKeyEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    label: OptionLabel
    explanation: str | None = None


class ParsedQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    number: int = Field(ge=1)
    difficulty: str | None = None
    prompt: str = Field(min_length=1)
    options: list[ParsedOption] = Field(min_length=1)
    correct_option_label: OptionLabel | None = None
    explanation: str | None = None

    @field_validator("options")
    @classmethod
    def unique_labels(cls, value: list[ParsedOption]) -> list[ParsedOption]:
        labels = [option.label for option in value]
        if len(labels) != len(set(labels)):
            raise ValueError("question options must have unique labels")
        return value


class ParsedLesson(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1)
    markdown: str
    slides: list[ParsedSlide]


class ParsedQuiz(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1)
    questions: list[ParsedQuestion] = Field(min_length=1)


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


_BULLET_LINE = re.compile(r"^\s*[-*]\s+(.+?)\s*$")
_BOLD = re.compile(r"\*\*(.+?)\*\*")


def parse_objectives_from_lesson(markdown: str) -> list[str]:
    """Extract learning-objective bullets from the first objectives slide."""
    slides = parse_slides(markdown)
    objectives_slide = next(
        (slide for slide in slides if "objective" in slide.title.lower()),
        slides[0] if slides else None,
    )
    if objectives_slide is None:
        return []

    objectives: list[str] = []
    for line in objectives_slide.content.splitlines():
        match = _BULLET_LINE.match(line)
        if not match:
            continue
        text = _BOLD.sub(r"\1", match.group(1)).strip()
        text = re.sub(r"\s+", " ", text)
        if text:
            objectives.append(text)
    return objectives


def _strip_answer_key(markdown: str) -> str:
    parts = _ANSWER_KEY_SPLIT.split(markdown, maxsplit=1)
    return parts[0].rstrip()


def _parse_answer_key(answer_section: str) -> dict[int, AnswerKeyEntry]:
    answers: dict[int, AnswerKeyEntry] = {}
    for match in _ANSWER_LINE.finditer(answer_section):
        number = int(match.group(1))
        label = match.group(2).strip().upper()
        if label in {"TRUE", "FALSE"}:
            label = "A" if label == "TRUE" else "B"
        explanation = match.group(3).strip() if match.group(3) else None
        answers[number] = AnswerKeyEntry(label=label, explanation=explanation)
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
        if not options or not prompt:
            continue
        answer = answers.get(number)
        questions.append(
            ParsedQuestion(
                number=number,
                difficulty=difficulty,
                prompt=prompt,
                options=options,
                correct_option_label=answer.label if answer else None,
                explanation=answer.explanation if answer else None,
            )
        )

    if not questions:
        raise ValueError(f"Quiz for '{topic_id}' has no parseable multiple-choice questions")
    if any(question.correct_option_label is None for question in questions):
        missing = [q.number for q in questions if q.correct_option_label is None]
        raise ValueError(f"Quiz for '{topic_id}' missing answer-key entries for: {missing}")

    return ParsedQuiz(title=title_from_markdown(markdown, topic_id), questions=questions)

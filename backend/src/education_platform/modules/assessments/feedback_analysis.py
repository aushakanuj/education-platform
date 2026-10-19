"""Level-specific feedback analysis.

Topic text names concepts. Subject text names topics. Overview text names
subjects. Each function builds one context, a deterministic paragraph, and a
prompt the summary worker can send to the model.

The paragraph is what the page shows when the model is unavailable. Model text
is kept only when it stays on that level and only links to URLs from the context.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from education_platform.modules.materials.markdown_parser import parse_slides

PASS_PERCENT = Decimal("70")
_LOW_PERCENT = Decimal("30")
_GUARD_MARKER = "ANALYSIS_GUARD"
_CONFIDENCE_LABELS = {
    "still_learning": "Still learning",
    "getting_it": "Getting it",
    "confident": "Confident",
}
_MD_HREF = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
_HTML_HREF = re.compile(r"""href=["']([^"']+)["']""", re.IGNORECASE)
_BARE_URL = re.compile(r"https?://[^\s)>\]]+")
_BARE_PATH = re.compile(r"(?<![A-Za-z0-9_])(/subjects/[^\s)>\]]+)")
_GUARD_BLOCK = re.compile(r"ANALYSIS_GUARD\s*(\{.*\})\s*\Z", re.DOTALL)

AnalysisLevel = Literal["topic", "subject", "overview"]


@dataclass(frozen=True, slots=True)
class ScoredItem:
    """One row at the level being described: a concept is not a row here.

    ``trend_samples`` is how many child rows produced ``trend_delta``. A subject
    trend is an aggregate only when that count is at least 2.
    """

    name: str
    percent: Decimal | None
    trend_delta: Decimal | None = None
    trend_samples: int = 0


@dataclass(frozen=True, slots=True)
class ConceptFact:
    name: str
    correct_count: int
    answered_count: int
    percent: Decimal


@dataclass(frozen=True, slots=True)
class StudyLink:
    """A published lesson the student can already open."""

    label: str
    href: str
    concept_names: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GoalFact:
    topic_name: str
    target_percent: Decimal
    gap_points: int


@dataclass(frozen=True, slots=True)
class TopicContext:
    topic_name: str
    concepts: tuple[ConceptFact, ...]
    trend_delta: Decimal | None
    goal_target: Decimal | None
    best_percent: Decimal | None
    confidence: str | None
    lesson_title: str | None
    lesson_href: str | None
    lesson_markdown: str | None
    extra_links: tuple[StudyLink, ...]
    forbidden_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SubjectContext:
    subject_name: str
    topics: tuple[ScoredItem, ...]
    trend_delta: Decimal | None
    confidence: str | None
    goals: tuple[GoalFact, ...]
    forbidden_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OverviewContext:
    subjects: tuple[ScoredItem, ...]
    ratings: tuple[tuple[str, str | None, Decimal | None], ...]
    forbidden_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AnalysisGuard:
    forbidden_names: tuple[str, ...]
    allowed_links: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AnalysisDraft:
    text: str
    prompt: str
    guard: AnalysisGuard


def topic_lesson_href(subject_id: str, topic_id: str) -> str:
    return f"/subjects/{subject_id}/topics/{topic_id}/lesson"


def subtopic_lesson_href(subject_id: str, subtopic_id: str) -> str:
    return f"/subjects/{subject_id}/subtopics/{subtopic_id}/lesson"


def topic_analysis(context: TopicContext) -> AnalysisDraft:
    """Actionable concept paragraph, plus only the published links in the context."""
    links = _topic_links(context)
    text = _compose(
        _topic_focus(context),
        _study_sentence(links, context.topic_name),
        _topic_trend(context.trend_delta),
        _goal_sentence(context.goal_target, context.best_percent),
        _topic_calibration(context.confidence, context.concepts),
    )
    guard = _guard(
        context.forbidden_names,
        tuple(concept.name for concept in context.concepts),
        tuple(link.href for link in links),
    )
    facts = {
        "level": "topic",
        "topic": context.topic_name,
        "concepts": [
            {
                "name": concept.name,
                "correct": concept.correct_count,
                "answered": concept.answered_count,
                "percent": _number(concept.percent),
            }
            for concept in context.concepts
        ],
        "trend_delta": _number(context.trend_delta),
        "goal_target": _number(context.goal_target),
        "best_percent": _number(context.best_percent),
        "self_rating": _confidence_label(context.confidence),
        "published_links": [{"label": link.label, "href": link.href} for link in links],
    }
    rules = (
        "Name 1 to 3 of the weakest concepts and why, using the correct and answered counts. "
        "Do not name other topics or subjects. "
        "Suggest study material only by linking the published_links, and no other URL. "
        "Mention the goal gap when a goal is present. "
        "Mention the self-rating when it is present, in terms of concepts."
    )
    return AnalysisDraft(text, _prompt("topic", rules, facts, text, guard), guard)


def subject_analysis(context: SubjectContext) -> AnalysisDraft:
    """Topic-level paragraph. Concept names stay in the guard, not the prose."""
    well, focus = _split(context.topics)
    text = _compose(
        _performance(well, focus, focus_phrase="next")
        or f"Take a topic quiz in {context.subject_name} to see where you stand.",
        _subject_trend(context.topics),
        _subject_calibration(context.confidence, context.topics),
    )
    guard = _guard(
        context.forbidden_names,
        tuple(topic.name for topic in context.topics),
        (),
    )
    facts = {
        "level": "subject",
        "subject": context.subject_name,
        "topics": [
            {
                "name": topic.name,
                "best_percent": _number(topic.percent),
                "trend_delta": _number(topic.trend_delta),
            }
            for topic in context.topics
        ],
        "repeated_topics": [
            {"name": topic.name, "change": _number(topic.trend_delta)}
            for topic in context.topics
            if topic.trend_delta is not None
        ],
        "self_rating": _confidence_label(context.confidence),
        "goals": [
            {
                "topic": goal.topic_name,
                "target_percent": _number(goal.target_percent),
                "gap_points": goal.gap_points,
            }
            for goal in context.goals
        ],
    }
    rules = (
        "Stay at topic level. Say which topics are going well and which to focus on next. "
        "Do not name concepts or subtopics. Do not include any link or URL. "
        "If one topic has a change since its previous attempt, name that topic and the points. "
        "If two or more topics have a change, give the average and say how many topics it covers. "
        "Do not describe one topic's change as a change across every topic. "
        "Calibrate the self-rating using topics."
    )
    return AnalysisDraft(text, _prompt("subject", rules, facts, text, guard), guard)


def overview_analysis(context: OverviewContext) -> AnalysisDraft:
    """Subject-level paragraph. Topic names stay in the guard, not the prose."""
    well, focus = _split(context.subjects)
    text = _compose(
        _performance(well, focus, focus_phrase="where")
        or "Take a topic quiz to see where you stand across subjects.",
        _overview_trend(context.subjects),
        _overview_calibration(context.ratings),
    )
    guard = _guard(
        context.forbidden_names,
        tuple(subject.name for subject in context.subjects),
        (),
    )
    facts = {
        "level": "overview",
        "subjects": [
            {
                "name": subject.name,
                "percent": _number(subject.percent),
                "aggregate_change": _number(subject.trend_delta)
                if subject.trend_samples >= 2
                else None,
                "topics_in_that_average": subject.trend_samples,
            }
            for subject in context.subjects
        ],
        "self_ratings": [
            {
                "subject": name,
                "rating": _confidence_label(confidence),
                "percent": _number(percent),
            }
            for name, confidence, percent in context.ratings
            if confidence
        ],
    }
    rules = (
        "Stay at subject level. Say which subjects are going well and which is where to focus. "
        "Do not name topics or concepts. Do not include any link or URL. "
        "Mention momentum only from aggregate_change, which is already a mean of two or more "
        "topics. If that field is null, leave momentum out. Never describe one topic's change "
        "as a change across subjects. "
        "Calibrate self-ratings using subject names only."
    )
    return AnalysisDraft(text, _prompt("overview", rules, facts, text, guard), guard)


def accept_model_text(model_text: str, template: str, prompt: str) -> tuple[str, bool]:
    """Keep model prose only when this prompt's guard allows it.

    A prompt with no guard is the older subject dashboard. That text is stored
    as the model wrote it. An empty reply, a broken guard, a lower-level name,
    or a link that was not in the context falls back to the template.
    """
    cleaned = model_text.strip()
    if not cleaned:
        return template, False
    parsed = _parse_guard(prompt)
    if parsed == "absent":
        return cleaned, True
    if parsed == "broken" or not _acceptable(cleaned, parsed):
        return template, False
    return cleaned, True


def _topic_links(context: TopicContext) -> tuple[StudyLink, ...]:
    if not context.lesson_href or not context.lesson_markdown:
        return _unique_links(context.extra_links)
    label = _markdown_label(f"{context.topic_name} lesson")
    links: list[StudyLink] = [StudyLink(label, context.lesson_href)]
    weak = _weak_concepts(context.concepts)
    slides = parse_slides(context.lesson_markdown)
    grouped: dict[tuple[int, str], list[str]] = {}
    for concept in weak:
        for slide in slides:
            haystack = f"{slide.title}\n{slide.content}"
            if _mentions(haystack, concept.name):
                grouped.setdefault((slide.number, slide.title), []).append(concept.name)
                break
    for (number, _title), names in grouped.items():
        href = f"{context.lesson_href}?slide={number}"
        slide_label = _markdown_label(f"{context.topic_name} lesson, slide {number}")
        links.append(StudyLink(slide_label, href, tuple(names)))
    links.extend(context.extra_links)
    return _unique_links(tuple(links))


def _unique_links(links: tuple[StudyLink, ...]) -> tuple[StudyLink, ...]:
    kept: list[StudyLink] = []
    seen: set[str] = set()
    for link in links:
        if not link.href or link.href in seen:
            continue
        seen.add(link.href)
        kept.append(link)
    return tuple(kept)


def _study_sentence(links: tuple[StudyLink, ...], topic_name: str) -> str | None:
    if not links:
        return None
    lesson = next((link for link in links if link.href and "?slide=" not in link.href), None)
    slides = [link for link in links if "?slide=" in link.href]
    parts: list[str] = []
    if len(slides) == 1:
        covered = slides[0].concept_names
        if len(covered) <= 1:
            parts.append(f"It is on {_md(slides[0])}.")
        elif len(covered) == 2:
            parts.append(f"Both are on {_md(slides[0])}.")
        else:
            parts.append(f"All {len(covered)} are on {_md(slides[0])}.")
    else:
        for link in slides:
            names = _join(list(link.concept_names))
            verb = "is" if len(link.concept_names) == 1 else "are"
            parts.append(f"{names} {verb} on {_md(link)}.")
    if not slides and lesson is not None and topic_name:
        parts.append(f"Review the {_md(lesson)}.")
    for link in links:
        if link in slides or (lesson is not None and link.href == lesson.href):
            continue
        parts.append(f"There is also a published {_md(link)}.")
    if not parts:
        return None
    return " ".join(parts)


def _topic_focus(context: TopicContext) -> str:
    weak = _weak_concepts(context.concepts)[:3]
    if weak:
        bits = [
            f"{concept.name} ({concept.correct_count} of {concept.answered_count} correct)"
            for concept in weak
        ]
        return f"Focus on {_join(bits)}."
    if context.concepts:
        best = max(context.concepts, key=lambda concept: (concept.percent, concept.name))
        return (
            "The concepts you tried are at 70% or above, including "
            f"{best.name} ({best.correct_count} of {best.answered_count} correct)."
        )
    return f"Take the {context.topic_name} quiz to see which ideas need work."


def _weak_concepts(concepts: tuple[ConceptFact, ...]) -> list[ConceptFact]:
    weak = [concept for concept in concepts if concept.percent < PASS_PERCENT]
    weak.sort(key=lambda concept: (concept.percent, concept.name))
    return weak


def _topic_trend(delta: Decimal | None) -> str | None:
    if delta is None:
        return None
    points = _points(delta)
    if points == 0:
        return "The last attempt matches the one before."
    if delta > 0:
        return f"The last attempt rose {points} points."
    return f"The last attempt dropped {points} points."


def _subject_trend(topics: tuple[ScoredItem, ...]) -> str | None:
    """Name a single mover. Average only when two or more topics actually moved."""
    moved = [topic for topic in topics if topic.trend_delta is not None]
    if not moved:
        return None
    if len(moved) == 1:
        topic = moved[0]
        delta = topic.trend_delta
        assert delta is not None
        points = _points(delta)
        if points == 0:
            return f"{topic.name} matched its previous attempt."
        verb = "rose" if delta > 0 else "dropped"
        return f"{topic.name} {verb} {points} points on the last attempt."
    deltas = [topic.trend_delta for topic in moved if topic.trend_delta is not None]
    return _average_change(deltas, f"the {len(moved)} topics with more than one attempt")


def _overview_trend(subjects: tuple[ScoredItem, ...]) -> str | None:
    """Use subject averages that already combine two or more topics. Otherwise stay quiet."""
    aggregates = [
        subject
        for subject in subjects
        if subject.trend_delta is not None and subject.trend_samples >= 2
    ]
    if not aggregates:
        return None
    if len(aggregates) == 1:
        subject = aggregates[0]
        delta = subject.trend_delta
        assert delta is not None
        points = _points(delta)
        if points == 0:
            return (
                f"{subject.name} is unchanged on average across its topics "
                "with more than one attempt."
            )
        direction = "up" if delta > 0 else "down"
        return (
            f"{subject.name} is {direction} {points} points on average across its topics "
            "with more than one attempt."
        )
    deltas = [subject.trend_delta for subject in aggregates if subject.trend_delta is not None]
    return _average_change(
        deltas,
        f"the {len(aggregates)} subjects with more than one repeated topic",
    )


def _average_change(deltas: list[Decimal], covered: str) -> str:
    mean = sum(deltas, Decimal("0")) / Decimal(len(deltas))
    points = _points(mean)
    if points == 0:
        return f"The average change is 0 points across {covered}."
    direction = "up" if mean > 0 else "down"
    return f"The average change is {direction} {points} points across {covered}."


def _goal_sentence(target: Decimal | None, best: Decimal | None) -> str | None:
    if target is None:
        return None
    target_points = int(target.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if best is None:
        return f"Your goal is {target_points}%."
    gap = int((target - best).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    best_points = int(best.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if gap > 0:
        return (
            f"Your goal is {target_points}%, and the best score is {best_points}%, "
            f"so {gap} points remain."
        )
    return f"Your goal of {target_points}% is already met."


def _topic_calibration(confidence: str | None, concepts: tuple[ConceptFact, ...]) -> str | None:
    label = _confidence_label(confidence)
    if label is None:
        return None
    under_30 = [concept for concept in concepts if concept.percent < _LOW_PERCENT]
    under_70 = [concept for concept in concepts if concept.percent < PASS_PERCENT]
    if confidence == "confident" and under_30:
        return (
            f"You said Confident, but {_count(len(under_30), 'concept')} under 30%; worth a review."
        )
    if confidence == "confident" and under_70:
        return (
            f"You said Confident, but {_count(len(under_70), 'concept')} under 70%; worth a review."
        )
    if confidence == "confident" and concepts:
        return "You said Confident, and the concepts you tried are at 70% or above."
    if confidence == "still_learning" and concepts and not under_70:
        return "You said Still learning, but the concepts you tried are at 70% or above."
    if confidence == "still_learning" and under_70:
        return f"You said Still learning, and {_count(len(under_70), 'concept')} under 70%."
    if confidence == "getting_it" and under_70:
        return f"You said Getting it. {_count(len(under_70), 'concept')} under 70%."
    if confidence == "getting_it" and concepts:
        return "You said Getting it, and the concepts you tried are at 70% or above."
    return f"You said {label}. The quiz will show how that lines up."


def _subject_calibration(confidence: str | None, topics: tuple[ScoredItem, ...]) -> str | None:
    label = _confidence_label(confidence)
    if label is None:
        return None
    _well, focus = _split(topics)
    named = focus[:3]
    if confidence == "confident" and named:
        return f"You said Confident, but {_join(named)} {_are(named)} under 70%."
    if confidence == "confident" and _well:
        return "You said Confident, and the topics you have tried are at 70% or above."
    if confidence == "still_learning" and _well and not named:
        return "You said Still learning, but the topics you have tried are at 70% or above."
    if confidence == "still_learning" and named:
        return f"You said Still learning, and {_join(named)} {_are(named)} under 70%."
    if confidence == "getting_it" and named:
        return f"You said Getting it. {_join(named)} {_are(named)} under 70%."
    if confidence == "getting_it" and _well:
        return "You said Getting it, and the topics you have tried are at 70% or above."
    return f"You said {label}. A topic quiz will show how that lines up."


def _overview_calibration(
    ratings: tuple[tuple[str, str | None, Decimal | None], ...],
) -> str | None:
    sentences: list[str] = []
    for name, confidence, percent in ratings:
        if _confidence_label(confidence) is None or percent is None:
            continue
        points = int(percent.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        if confidence == "confident" and percent < PASS_PERCENT:
            sentences.append(f"You said Confident in {name}, but that subject is under 70%.")
        elif confidence == "still_learning" and percent >= Decimal("80"):
            sentences.append(
                f"You said Still learning in {name}, but that subject is at {points}%."
            )
        elif confidence == "getting_it" and percent < Decimal("50"):
            sentences.append(f"You said Getting it in {name}, and that subject is under 50%.")
    if not sentences:
        return None
    return " ".join(sentences)


def _split(items: tuple[ScoredItem, ...] | list[ScoredItem]) -> tuple[list[str], list[str]]:
    scored: list[tuple[str, Decimal]] = []
    for item in items:
        percent = item.percent
        if percent is not None:
            scored.append((item.name, percent))
    well = sorted(
        [row for row in scored if row[1] >= PASS_PERCENT],
        key=lambda row: (-row[1], row[0]),
    )
    focus = sorted(
        [row for row in scored if row[1] < PASS_PERCENT],
        key=lambda row: (row[1], row[0]),
    )
    return [name for name, _percent in well], [name for name, _percent in focus]


def _performance(
    well: list[str], focus: list[str], *, focus_phrase: Literal["next", "where"]
) -> str:
    well = well[:3]
    focus = focus[:3]
    if well and focus and focus_phrase == "next":
        return f"{_join(well)} {_are(well)} going well; focus next on {_join(focus)}."
    if well and focus:
        return (
            f"{_join(well)} {_are(well)} going well; {_join(focus)} {_are(focus)} where to focus."
        )
    if well:
        return f"{_join(well)} {_are(well)} going well."
    if focus and focus_phrase == "next":
        return f"Focus next on {_join(focus)}."
    if focus:
        return f"{_join(focus)} {_are(focus)} where to focus."
    return ""


def _prompt(
    level: AnalysisLevel,
    rules: str,
    facts: Mapping[str, object],
    template: str,
    guard: AnalysisGuard,
) -> str:
    payload = {"level": level, "facts": facts, "template": template}
    guard_json = json.dumps(
        {
            "forbidden_names": list(guard.forbidden_names),
            "allowed_links": list(guard.allowed_links),
        },
        ensure_ascii=False,
    )
    return (
        f"Write one short paragraph of student feedback at the {level} level.\n"
        f"{rules}\n"
        "Use only the facts. Do not invent scores, names, titles, or links.\n"
        "If you mention a link, use a markdown link and only a URL from allowed_links.\n"
        "Do not repeat this instruction block or the guard.\n\n"
        f"FACTS\n{json.dumps(payload, ensure_ascii=False)}\n\n"
        f"{_GUARD_MARKER}\n{guard_json}\n"
    )


def _guard(
    forbidden: tuple[str, ...],
    allowed_names: tuple[str, ...],
    links: tuple[str, ...],
) -> AnalysisGuard:
    allowed = {name.casefold() for name in allowed_names if name.strip()}
    kept: list[str] = []
    seen: set[str] = set()
    for name in forbidden:
        cleaned = name.strip()
        folded = cleaned.casefold()
        if len(cleaned) < 2 or folded in allowed or folded in seen:
            continue
        seen.add(folded)
        kept.append(cleaned)
    hrefs: list[str] = []
    seen_hrefs: set[str] = set()
    for href in links:
        if href and href not in seen_hrefs:
            seen_hrefs.add(href)
            hrefs.append(href)
    return AnalysisGuard(tuple(kept), tuple(hrefs))


def _parse_guard(prompt: str) -> AnalysisGuard | Literal["absent", "broken"]:
    if _GUARD_MARKER not in prompt:
        return "absent"
    match = _GUARD_BLOCK.search(prompt)
    if match is None:
        return "broken"
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return "broken"
    if not isinstance(payload, dict):
        return "broken"
    forbidden = payload.get("forbidden_names")
    allowed = payload.get("allowed_links")
    if not isinstance(forbidden, list) or not isinstance(allowed, list):
        return "broken"
    if not all(isinstance(name, str) for name in forbidden):
        return "broken"
    if not all(isinstance(href, str) for href in allowed):
        return "broken"
    return AnalysisGuard(tuple(forbidden), tuple(allowed))


def _acceptable(text: str, guard: AnalysisGuard) -> bool:
    if _GUARD_MARKER in text:
        return False
    if any(_mentions(text, name) for name in guard.forbidden_names):
        return False
    allowed = set(guard.allowed_links)
    return all(href in allowed for href in _hrefs(text))


def _hrefs(text: str) -> set[str]:
    found: set[str] = set()
    for pattern in (_MD_HREF, _HTML_HREF, _BARE_URL, _BARE_PATH):
        for match in pattern.findall(text):
            href = match.rstrip(".,;")
            if href:
                found.add(href)
    return found


def _mentions(text: str, name: str) -> bool:
    cleaned = name.strip()
    if len(cleaned) < 2:
        return False
    pattern = rf"(?<!\w){re.escape(cleaned)}(?!\w)"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _compose(*parts: str | None) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


def _join(names: list[str]) -> str:
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return f"{', '.join(names[:-1])}, and {names[-1]}"


def _are(names: list[str]) -> str:
    return "is" if len(names) == 1 else "are"


def _count(amount: int, noun: str) -> str:
    if amount == 1:
        return f"1 {noun} is"
    return f"{amount} {noun}s are"


def _points(value: Decimal) -> int:
    return int(abs(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _number(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _confidence_label(confidence: str | None) -> str | None:
    if confidence is None:
        return None
    return _CONFIDENCE_LABELS.get(confidence)


def _markdown_label(label: str) -> str:
    cleaned = re.sub(r"\s+", " ", label).replace("[", "").replace("]", "").strip()
    return cleaned or "Lesson"


def _md(link: StudyLink) -> str:
    return f"[{_markdown_label(link.label)}]({link.href})"

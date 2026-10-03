"""Per-item statistics from real student attempts.

Flags are withheld until an item has at least ``MIN_RESPONSES`` counted answers.
Threshold comparisons are strict. A negative point-biserial is also below the
low-discrimination cutoff, so both flags are reported.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.modules.assessments.models import (
    AttemptAnswer,
    QuestionAnswerKey,
    QuestionOption,
    QuestionVersion,
    QuizAttempt,
    QuizAttemptStatus,
    QuizItem,
    QuizScope,
)
from education_platform.modules.assessments.queries import released_quiz

MIN_RESPONSES = 20
TOO_EASY_P_CORRECT = 0.95
TOO_HARD_P_CORRECT = 0.20
LOW_DISCRIMINATION = 0.15
NEGATIVE_DISCRIMINATION = 0.0
DEAD_DISTRACTOR_PICK_RATE = 0.05
TOP_BOTTOM_FRACTION = 0.27

COUNTED_ATTEMPT_STATUSES = (
    QuizAttemptStatus.SUBMITTED,
    QuizAttemptStatus.SCORED,
    QuizAttemptStatus.RELEASED,
)

ItemFlag = Literal[
    "too_easy",
    "too_hard",
    "low_discrimination",
    "negative_discrimination",
    "dead_distractor",
    "distractor_beats_key_top_group",
]


class ItemOptionStat(BaseModel):
    label: str
    text: str
    is_key: bool
    pick_rate: float
    top_group_pick_rate: float
    bottom_group_pick_rate: float


class ItemStat(BaseModel):
    question_version_id: UUID
    sequence: int
    prompt: str
    correct_option_label: str | None
    n: int
    p_correct: float | None
    discrimination: float | None
    options: list[ItemOptionStat]
    flags: list[ItemFlag]


class TopicItemStats(BaseModel):
    topic_id: UUID
    quiz_version_id: UUID | None
    minimum_n: int
    items: list[ItemStat]


@dataclass(frozen=True)
class _Response:
    attempt_id: UUID
    attempt_number: int
    is_correct: bool
    rest_score: float
    selected_label: str | None


def _extreme_group_size(n: int) -> int:
    """Kelley's 27% tails, rounded half up, capped so the two tails do not overlap."""
    if n < 2:
        return 0
    size = int(n * TOP_BOTTOM_FRACTION + 0.5)
    return min(max(size, 1), n // 2)


def _rate(count: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return count / denominator


def _rest_score(
    attempt: QuizAttempt,
    answer: AttemptAnswer,
    marks_by_question: dict[UUID, Decimal | None],
) -> float:
    """Attempt score excluding this item.

    Prefer ``score_raw - marks_awarded``. When the attempt has not rolled a total
    up yet, sum the marks awarded on the other items of the same quiz.
    """
    if attempt.score_raw is not None and answer.marks_awarded is not None:
        return float(attempt.score_raw - answer.marks_awarded)
    others = [
        marks
        for question_id, marks in marks_by_question.items()
        if question_id != answer.question_version_id and marks is not None
    ]
    return float(sum(others, start=Decimal("0")))


def _point_biserial(correct: list[bool], rest: list[float]) -> float | None:
    """Pearson correlation of item correctness with the attempt rest-score."""
    n = len(correct)
    if n < 2:
        return None
    scores = [1.0 if flag else 0.0 for flag in correct]
    mean_score = sum(scores) / n
    mean_rest = sum(rest) / n
    pairs = zip(scores, rest, strict=True)
    covariance = sum((score - mean_score) * (value - mean_rest) for score, value in pairs)
    score_ss = sum((score - mean_score) ** 2 for score in scores)
    rest_ss = sum((value - mean_rest) ** 2 for value in rest)
    if score_ss == 0 or rest_ss == 0:
        return None
    return covariance / math.sqrt(score_ss * rest_ss)


def _flags(
    *,
    n: int,
    p_correct: float | None,
    discrimination: float | None,
    dead_distractor: bool,
    distractor_beats_key: bool,
) -> list[ItemFlag]:
    if n < MIN_RESPONSES or p_correct is None:
        return []
    found: list[ItemFlag] = []
    if p_correct > TOO_EASY_P_CORRECT:
        found.append("too_easy")
    if p_correct < TOO_HARD_P_CORRECT:
        found.append("too_hard")
    if discrimination is not None and discrimination < LOW_DISCRIMINATION:
        found.append("low_discrimination")
    if discrimination is not None and discrimination < NEGATIVE_DISCRIMINATION:
        found.append("negative_discrimination")
    if dead_distractor:
        found.append("dead_distractor")
    if distractor_beats_key:
        found.append("distractor_beats_key_top_group")
    return found


async def _responses_by_question(
    session: AsyncSession, quiz_version_id: UUID
) -> dict[UUID, list[_Response]]:
    rows = (
        await session.execute(
            select(AttemptAnswer, QuizAttempt)
            .join(QuizAttempt, AttemptAnswer.attempt_id == QuizAttempt.id)
            .join(
                QuizItem,
                and_(
                    QuizItem.quiz_version_id == QuizAttempt.quiz_version_id,
                    QuizItem.question_version_id == AttemptAnswer.question_version_id,
                ),
            )
            .where(
                QuizAttempt.quiz_version_id == quiz_version_id,
                QuizAttempt.status.in_(COUNTED_ATTEMPT_STATUSES),
                AttemptAnswer.is_correct.is_not(None),
            )
        )
    ).all()

    by_attempt: dict[UUID, list[tuple[AttemptAnswer, QuizAttempt]]] = {}
    for answer, attempt in rows:
        by_attempt.setdefault(attempt.id, []).append((answer, attempt))

    grouped: dict[UUID, list[_Response]] = {}
    for attempt_rows in by_attempt.values():
        attempt = attempt_rows[0][1]
        marks_by_question = {
            answer.question_version_id: answer.marks_awarded for answer, _attempt in attempt_rows
        }
        for answer, _attempt in attempt_rows:
            grouped.setdefault(answer.question_version_id, []).append(
                _Response(
                    attempt_id=attempt.id,
                    attempt_number=attempt.attempt_number,
                    is_correct=bool(answer.is_correct),
                    rest_score=_rest_score(attempt, answer, marks_by_question),
                    selected_label=answer.selected_option_label,
                )
            )
    return grouped


def _item_stat(
    item: QuizItem,
    version: QuestionVersion,
    options: list[QuestionOption],
    key: QuestionAnswerKey | None,
    responses: list[_Response],
) -> ItemStat:
    # Higher rest-score first. Equal scores break toward the earlier attempt so
    # the 27% tails stay stable when many attempts share a score.
    ranked = sorted(
        responses,
        key=lambda row: (-row.rest_score, row.attempt_number, str(row.attempt_id)),
    )
    n = len(ranked)
    correct_count = sum(1 for row in ranked if row.is_correct)
    p_correct = correct_count / n if n else None
    discrimination = _point_biserial(
        [row.is_correct for row in ranked],
        [row.rest_score for row in ranked],
    )
    group_size = _extreme_group_size(n)
    top = ranked[:group_size]
    bottom = ranked[-group_size:] if group_size else []
    correct_label = key.correct_option_label if key is not None else None
    key_top_count = (
        sum(1 for row in top if row.selected_label == correct_label) if correct_label else 0
    )

    option_stats: list[ItemOptionStat] = []
    dead_distractor = False
    distractor_beats_key = False
    for option in options:
        picked = sum(1 for row in ranked if row.selected_label == option.label)
        top_picked = sum(1 for row in top if row.selected_label == option.label)
        bottom_picked = sum(1 for row in bottom if row.selected_label == option.label)
        is_key = correct_label is not None and option.label == correct_label
        pick_rate = _rate(picked, n)
        if correct_label is not None and not is_key and pick_rate < DEAD_DISTRACTOR_PICK_RATE:
            dead_distractor = True
        if correct_label is not None and not is_key and top_picked > key_top_count:
            distractor_beats_key = True
        option_stats.append(
            ItemOptionStat(
                label=option.label,
                text=option.text,
                is_key=is_key,
                pick_rate=pick_rate,
                top_group_pick_rate=_rate(top_picked, group_size),
                bottom_group_pick_rate=_rate(bottom_picked, group_size),
            )
        )

    return ItemStat(
        question_version_id=version.id,
        sequence=item.sequence,
        prompt=version.prompt,
        correct_option_label=correct_label,
        n=n,
        p_correct=p_correct,
        discrimination=discrimination,
        options=option_stats,
        flags=_flags(
            n=n,
            p_correct=p_correct,
            discrimination=discrimination,
            dead_distractor=dead_distractor,
            distractor_beats_key=distractor_beats_key,
        ),
    )


async def item_stats_for_quiz_version(
    session: AsyncSession, quiz_version_id: UUID
) -> list[ItemStat]:
    """Statistics for every item on a quiz version, in quiz sequence."""
    items = (
        await session.scalars(
            select(QuizItem)
            .where(QuizItem.quiz_version_id == quiz_version_id)
            .order_by(QuizItem.sequence)
        )
    ).all()
    if not items:
        return []

    question_ids = [item.question_version_id for item in items]
    versions = {
        version.id: version
        for version in (
            await session.scalars(
                select(QuestionVersion).where(QuestionVersion.id.in_(question_ids))
            )
        ).all()
    }
    options_by_question: dict[UUID, list[QuestionOption]] = {qid: [] for qid in question_ids}
    for option in (
        await session.scalars(
            select(QuestionOption)
            .where(QuestionOption.question_version_id.in_(question_ids))
            .order_by(QuestionOption.sequence, QuestionOption.label)
        )
    ).all():
        options_by_question.setdefault(option.question_version_id, []).append(option)
    keys = {
        key.question_version_id: key
        for key in (
            await session.scalars(
                select(QuestionAnswerKey).where(
                    QuestionAnswerKey.question_version_id.in_(question_ids)
                )
            )
        ).all()
    }
    responses = await _responses_by_question(session, quiz_version_id)
    return [
        _item_stat(
            item,
            versions[item.question_version_id],
            options_by_question.get(item.question_version_id, []),
            keys.get(item.question_version_id),
            responses.get(item.question_version_id, []),
        )
        for item in items
        if item.question_version_id in versions
    ]


async def item_stats_for_topic(session: AsyncSession, topic_id: UUID) -> TopicItemStats:
    """Stats for the topic's latest released topic-mastery quiz, if one exists."""
    released = await released_quiz(session, quiz_scope=QuizScope.TOPIC_MASTERY, target_id=topic_id)
    if released is None:
        return TopicItemStats(
            topic_id=topic_id,
            quiz_version_id=None,
            minimum_n=MIN_RESPONSES,
            items=[],
        )
    _quiz, version = released
    return TopicItemStats(
        topic_id=topic_id,
        quiz_version_id=version.id,
        minimum_n=MIN_RESPONSES,
        items=await item_stats_for_quiz_version(session, version.id),
    )

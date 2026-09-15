"""Python-owned bank and quiz mix. The LLM cannot override these constants."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from education_platform.modules.assessments.models import QuestionDifficulty, QuestionItemKind
from education_platform.modules.generation.types import BloomLevel

BANK_SIZE = 80
BANK_THEORY = 20
BANK_PROBLEM = 60
BANK_EASY = 32
BANK_MEDIUM = 32
BANK_HARD = 16

QUIZ_SIZE = 10
QUIZ_THEORY = 2
QUIZ_PROBLEM = 8
QUIZ_EASY = 4
QUIZ_MEDIUM = 4
QUIZ_HARD = 2

ITEM_BATCH_MIN = 10
ITEM_BATCH_MAX = 16

MIN_CONCEPT_PROSE_CHARS = 240

# Curriculum bank slots: 20 theory / 60 problem and 32 easy / 32 medium / 16 hard.
# Bloom is assigned so remember/understand → easy, apply → medium, analyze → hard.
_CURRICULUM_SLOT_RECIPE: tuple[
    tuple[QuestionItemKind, QuestionDifficulty, BloomLevel, int], ...
] = (
    (QuestionItemKind.THEORY, QuestionDifficulty.EASY, BloomLevel.REMEMBER, 8),
    (QuestionItemKind.THEORY, QuestionDifficulty.MEDIUM, BloomLevel.APPLY, 8),
    (QuestionItemKind.THEORY, QuestionDifficulty.HARD, BloomLevel.ANALYZE, 4),
    (QuestionItemKind.PROBLEM, QuestionDifficulty.EASY, BloomLevel.UNDERSTAND, 24),
    (QuestionItemKind.PROBLEM, QuestionDifficulty.MEDIUM, BloomLevel.APPLY, 24),
    (QuestionItemKind.PROBLEM, QuestionDifficulty.HARD, BloomLevel.ANALYZE, 12),
)


@dataclass(frozen=True, slots=True)
class MixCounts:
    total: int
    theory: int
    problem: int
    easy: int
    medium: int
    hard: int


class MixError(ValueError):
    """Bank or assembled quiz does not match the blueprint."""


def counts_for(
    items: Sequence[tuple[QuestionItemKind, QuestionDifficulty]],
) -> MixCounts:
    theory = sum(1 for kind, _difficulty in items if kind is QuestionItemKind.THEORY)
    problem = sum(1 for kind, _difficulty in items if kind is QuestionItemKind.PROBLEM)
    easy = sum(1 for _kind, difficulty in items if difficulty is QuestionDifficulty.EASY)
    medium = sum(1 for _kind, difficulty in items if difficulty is QuestionDifficulty.MEDIUM)
    hard = sum(1 for _kind, difficulty in items if difficulty is QuestionDifficulty.HARD)
    return MixCounts(
        total=len(items),
        theory=theory,
        problem=problem,
        easy=easy,
        medium=medium,
        hard=hard,
    )


def check_bank_mix(items: Sequence[tuple[QuestionItemKind, QuestionDifficulty]]) -> str | None:
    mix = counts_for(items)
    if mix.total != BANK_SIZE:
        return f"Question bank must have {BANK_SIZE} items; got {mix.total}."
    if mix.theory != BANK_THEORY or mix.problem != BANK_PROBLEM:
        return (
            f"Question bank must be {BANK_THEORY} theory and {BANK_PROBLEM} problem; "
            f"got {mix.theory} theory and {mix.problem} problem."
        )
    if mix.easy != BANK_EASY or mix.medium != BANK_MEDIUM or mix.hard != BANK_HARD:
        return (
            f"Question bank difficulty must be {BANK_EASY} easy / {BANK_MEDIUM} medium / "
            f"{BANK_HARD} hard; got {mix.easy} / {mix.medium} / {mix.hard}."
        )
    return None


def check_quiz_mix(items: Sequence[tuple[QuestionItemKind, QuestionDifficulty]]) -> str | None:
    mix = counts_for(items)
    if mix.total != QUIZ_SIZE:
        return f"Mastery quiz must have {QUIZ_SIZE} items; got {mix.total}."
    if mix.theory != QUIZ_THEORY or mix.problem != QUIZ_PROBLEM:
        return (
            f"Mastery quiz must be {QUIZ_THEORY} theory and {QUIZ_PROBLEM} problem; "
            f"got {mix.theory} theory and {mix.problem} problem."
        )
    if mix.easy != QUIZ_EASY or mix.medium != QUIZ_MEDIUM or mix.hard != QUIZ_HARD:
        return (
            f"Mastery quiz difficulty must be {QUIZ_EASY} easy / {QUIZ_MEDIUM} medium / "
            f"{QUIZ_HARD} hard; got {mix.easy} / {mix.medium} / {mix.hard}."
        )
    return None


def curriculum_item_slots() -> tuple[tuple[QuestionItemKind, QuestionDifficulty, BloomLevel], ...]:
    """Python-owned 80-item mix. The LLM cannot override kind, difficulty, or Bloom."""
    slots: list[tuple[QuestionItemKind, QuestionDifficulty, BloomLevel]] = []
    for kind, difficulty, bloom, count in _CURRICULUM_SLOT_RECIPE:
        slots.extend([(kind, difficulty, bloom)] * count)
    return tuple(slots)


def assemble_mastery_indexes(
    items: Sequence[tuple[QuestionItemKind, QuestionDifficulty]],
) -> tuple[int, ...] | str:
    """Pick 10 bank indexes: 2 theory / 8 problem and 4 easy / 4 medium / 2 hard.

    Deterministic: lowest index in each bucket wins. Returns an error string if
    the bank cannot fill the assembled mix.
    """
    buckets: dict[tuple[QuestionItemKind, QuestionDifficulty], list[int]] = {}
    for index, pair in enumerate(items):
        buckets.setdefault(pair, []).append(index)

    def take(kind: QuestionItemKind, difficulty: QuestionDifficulty, count: int) -> list[int] | str:
        pool = buckets.get((kind, difficulty), [])
        if len(pool) < count:
            return (
                f"Cannot assemble the 10-item quiz: need {count} {difficulty.value} "
                f"{kind.value} items, found {len(pool)}."
            )
        chosen = pool[:count]
        buckets[(kind, difficulty)] = pool[count:]
        return chosen

    picked: list[int] = []
    # 1 theory easy, 1 theory medium, 3 problem easy, 3 problem medium, 2 problem hard.
    recipe = (
        (QuestionItemKind.THEORY, QuestionDifficulty.EASY, 1),
        (QuestionItemKind.THEORY, QuestionDifficulty.MEDIUM, 1),
        (QuestionItemKind.PROBLEM, QuestionDifficulty.EASY, 3),
        (QuestionItemKind.PROBLEM, QuestionDifficulty.MEDIUM, 3),
        (QuestionItemKind.PROBLEM, QuestionDifficulty.HARD, 2),
    )
    for kind, difficulty, count in recipe:
        taken = take(kind, difficulty, count)
        if isinstance(taken, str):
            return taken
        picked.extend(taken)
    picked.sort()
    mix_error = check_quiz_mix(tuple(items[index] for index in picked))
    if mix_error is not None:
        return mix_error
    return tuple(picked)

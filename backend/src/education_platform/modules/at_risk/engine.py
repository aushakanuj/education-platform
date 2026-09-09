"""At-risk rule engine — pure functions, no I/O. See docs/design/08-at-risk-early-warning.md."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

# Threshold derivation (spec §6.2):
# - MASTERY_LEVEL_THRESHOLD = 60.0 — synthetic school mean 71.3%, SD 8.5; 1.5 SD below ≈ 58.5%.
#   Flags ~11.5% of student-subject rows.
# - MASTERY_TREND_DECLINE_THRESHOLD = 15.0 — decline past 15 points in ~2.9% of groups with history.
# - ATTENDANCE_LEVEL_THRESHOLD = 80.0 — gap between 70% cluster and next at 86%;
#   not the old 75% demo value.
# - No attendance trend in v1 — `student_360.attendance_percent` is cumulative, not a series.
# Recalibrate against other schools before reusing these defaults.


@dataclass(frozen=True, slots=True)
class Thresholds:
    mastery_level: float = 60.0
    mastery_trend_decline: float = 15.0
    mastery_trend_recent_window: int = 3
    mastery_trend_min_earlier_attempts: int = 2
    attendance_level: float = 80.0


DEFAULT_THRESHOLDS = Thresholds()


@dataclass(frozen=True, slots=True)
class Driver:
    metric: str
    value: float
    comparison: str
    window: str


@dataclass(frozen=True, slots=True)
class EngineFlag:
    grade_subject_offering_id: UUID | None
    tier: str
    drivers: tuple[Driver, ...]

    def __post_init__(self) -> None:
        if not self.drivers:
            raise ValueError("AR-1: a flag must name at least one driver.")


@dataclass(frozen=True, slots=True)
class SubjectSignal:
    grade_subject_offering_id: UUID
    mastery_percent: float
    attempt_scores_recent_first: tuple[float, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class StudentSignals:
    student_id: UUID
    attendance_percent: float | None
    subjects: tuple[SubjectSignal, ...]


def _mastery_trend_driver(signal: SubjectSignal, thresholds: Thresholds) -> Driver | None:
    scores = signal.attempt_scores_recent_first
    recent = scores[: thresholds.mastery_trend_recent_window]
    earlier = scores[thresholds.mastery_trend_recent_window :]
    if len(earlier) < thresholds.mastery_trend_min_earlier_attempts or not recent:
        return None

    recent_avg = sum(recent) / len(recent)
    earlier_avg = sum(earlier) / len(earlier)
    decline = earlier_avg - recent_avg
    if decline <= thresholds.mastery_trend_decline:
        return None

    return Driver(
        metric="mastery_trend",
        value=round(decline, 2),
        comparison=(
            f"declined {decline:.1f} points (threshold {thresholds.mastery_trend_decline:.1f})"
        ),
        window=(
            f"last {len(recent)} attempts ({recent_avg:.1f}% avg) vs "
            f"earlier {len(earlier)} attempts ({earlier_avg:.1f}% avg)"
        ),
    )


def _mastery_level_driver(signal: SubjectSignal, thresholds: Thresholds) -> Driver | None:
    if signal.mastery_percent >= thresholds.mastery_level:
        return None
    return Driver(
        metric="mastery_percent",
        value=signal.mastery_percent,
        comparison=f"below {thresholds.mastery_level:.1f}",
        window="single reading",
    )


def _attendance_level_driver(attendance_percent: float, thresholds: Thresholds) -> Driver | None:
    if attendance_percent >= thresholds.attendance_level:
        return None
    return Driver(
        metric="attendance_percent",
        value=attendance_percent,
        comparison=f"below {thresholds.attendance_level:.1f}",
        window="single reading",
    )


def _tier_for(drivers: tuple[Driver, ...]) -> str:
    if len(drivers) >= 2:
        return "urgent"
    if drivers[0].metric == "mastery_trend":
        return "attention"
    return "monitor"


def evaluate_subject(
    signal: SubjectSignal, thresholds: Thresholds = DEFAULT_THRESHOLDS
) -> EngineFlag | None:
    drivers = tuple(
        driver
        for driver in (
            _mastery_level_driver(signal, thresholds),
            _mastery_trend_driver(signal, thresholds),
        )
        if driver is not None
    )
    if not drivers:
        return None
    return EngineFlag(
        grade_subject_offering_id=signal.grade_subject_offering_id,
        tier=_tier_for(drivers),
        drivers=drivers,
    )


def evaluate_attendance(
    attendance_percent: float | None, thresholds: Thresholds = DEFAULT_THRESHOLDS
) -> EngineFlag | None:
    if attendance_percent is None:
        return None
    driver = _attendance_level_driver(attendance_percent, thresholds)
    if driver is None:
        return None
    return EngineFlag(grade_subject_offering_id=None, tier=_tier_for((driver,)), drivers=(driver,))


def evaluate_student(
    signals: StudentSignals, thresholds: Thresholds = DEFAULT_THRESHOLDS
) -> list[EngineFlag]:
    flags = [evaluate_subject(subject, thresholds) for subject in signals.subjects]
    flags.append(evaluate_attendance(signals.attendance_percent, thresholds))
    return [flag for flag in flags if flag is not None]

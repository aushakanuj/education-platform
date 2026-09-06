"""The at-risk rule engine: pure functions, no database, no I/O.

Implements docs/design/08-at-risk-early-warning.md Sections 5 and 6. Deliberately
dependency-free -- everything a caller needs is passed in as plain data (`StudentSignals`)
and everything that comes out is plain data (`EngineFlag`). That is what makes this
testable with 40+ named cases and no database: the DB-touching part (`service.py`) is a
thin translation layer on either side of this file, not where the rule lives.

**Threshold derivation, not guesses** (the spec's Section 6.2 requires this to be shown,
not asserted):

- `MASTERY_LEVEL_THRESHOLD = 60.0` -- the synthetic school's 1,201 student-subject rows
  have a mean mastery of 71.3% and a standard deviation of 8.5 points (computed 29 Aug
  2026 against the live database). One and a half standard deviations below the mean is
  58.5%; 60% is that same cut rounded to a number a teacher can say out loud. It flags
  138 of 1,201 rows (~11.5%) -- a minority, not a near-miss and not a landslide.
- `MASTERY_TREND_DECLINE_THRESHOLD = 15.0` -- computed from every student-subject with at
  least two earlier attempts to compare against (1,200 such groups). A decline past 15
  points between the earliest attempts' average and the latest 3 occurs in 35 of them
  (~2.9%). Aisha Rahman's real Mathematics sequence (74, 65, 56, 47, 38) produces a 22.5
  point decline under this exact comparison -- comfortably past 15. Her 56% average is
  *also* below the 60% level threshold, so her Mathematics flag correctly carries both
  drivers and lands at "urgent" (Section 6.1's two-independent-signals-agree case) --
  she is not the case that proves trend is necessary on its own. That case is any student
  whose *current* average still sits above the level threshold but who has clearly
  slid -- level alone would clear them; trend catches them. `test_at_risk_engine.py`
  covers both shapes separately rather than asking one student to illustrate both.
- `ATTENDANCE_LEVEL_THRESHOLD = 80.0` -- the school's attendance values have a real, clean
  gap: 15 students sit at or below 70% (Aisha Rahman at 62%, fourteen others clustered
  exactly at 70%), and then nobody at all until 86%. 80% sits in that gap. It is not the
  old placeholder's 75% reused -- that number was picked for demo plausibility (see spec
  Section 10); this one is read off a real discontinuity in the actual data.
- Attendance has no trend check in this version -- `student_360.attendance_percent` is one
  cumulative figure, not a per-attempt series like quiz scores are, so a trend would need
  to read `attendance_records` day-by-day. Documented as a deliberate v1 boundary, not an
  oversight -- see the module README / handover doc for the follow-up.

Recalibrate these against a different school's data before trusting them there -- they are
derived from this synthetic school's actual distribution, not universal constants.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Thresholds:
    """Every number the engine compares against, in one place, with a default that is
    documented (not just typed) at the top of this file. Pass a different instance to
    recalibrate without touching the rule logic itself."""

    mastery_level: float = 60.0
    mastery_trend_decline: float = 15.0
    mastery_trend_recent_window: int = 3
    mastery_trend_min_earlier_attempts: int = 2
    attendance_level: float = 80.0


DEFAULT_THRESHOLDS = Thresholds()


@dataclass(frozen=True, slots=True)
class Driver:
    """One named reason a flag exists. AR-1 in the spec: a flag with no drivers must not
    exist, and this is the type that makes that concrete -- there is no way to build an
    `EngineFlag` without at least one of these."""

    metric: str  # "mastery_percent" | "mastery_trend" | "attendance_percent"
    value: float  # the actual number, at the time of computation
    comparison: str  # e.g. "below 60.0" or "declined 22.5 points (threshold 15.0)"
    window: str  # "single reading" | "last 3 vs earlier N attempts"


@dataclass(frozen=True, slots=True)
class EngineFlag:
    grade_subject_offering_id: UUID | None  # None only for an attendance-only flag
    tier: str  # "monitor" | "attention" | "urgent"
    drivers: tuple[Driver, ...]

    def __post_init__(self) -> None:
        if not self.drivers:
            raise ValueError(
                "AR-1: a flag must name at least one driver. If nothing can be named as "
                "the reason, do not construct a flag at all -- return no flag instead."
            )


@dataclass(frozen=True, slots=True)
class SubjectSignal:
    """One student's standing in one subject, exactly as `student_360` and the quiz
    attempt history already carry it -- no derived numbers computed before this point."""

    grade_subject_offering_id: UUID
    mastery_percent: float
    #: Most recent attempts first. Pass every scored attempt available; the engine takes
    #: its own recent/earlier split from `thresholds`, so it does not need pre-slicing.
    attempt_scores_recent_first: tuple[float, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class StudentSignals:
    """Everything the engine needs about one student to decide every flag they might get.

    One instance covers all of a student's subjects plus their (whole-student) attendance
    -- the natural unit of computation, since attendance is evaluated once per student
    while mastery is evaluated once per subject (spec Section 2's signal-grain decision).
    """

    student_id: UUID
    attendance_percent: float | None
    subjects: tuple[SubjectSignal, ...]


def _mastery_trend_driver(signal: SubjectSignal, thresholds: Thresholds) -> Driver | None:
    """A significant decline between a student's earliest and most recent attempts in one
    subject. Returns None when there is not enough history to compare, which is the
    correct answer for a new student -- not a flag, and not an error either."""
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
    """Three tiers, each explainable in one sentence (spec Section 14 flags tier *names*
    as a communication choice worth a second opinion -- these are a first draft, not
    a settled decision):

    - urgent: two or more independent signals agree (e.g. a subject is both low *and*
      actively declining, or a subject concern coincides with an attendance concern).
    - attention: exactly one signal, and it is a trend -- a moving trajectory is more
      time-sensitive than a steady number, even a low one.
    - monitor: exactly one signal, and it is a level reading with nothing moving.
    """
    if len(drivers) >= 2:
        return "urgent"
    if drivers[0].metric == "mastery_trend":
        return "attention"
    return "monitor"


def evaluate_subject(
    signal: SubjectSignal, thresholds: Thresholds = DEFAULT_THRESHOLDS
) -> EngineFlag | None:
    """One subject's flag, or None if neither condition fires.

    Deliberately two separate checks, never one blended score: averaging a low level with
    a fine trend (or vice versa) would hide exactly the "strong everywhere except one
    subject" pattern the spec's Section 6.1 requires this engine to preserve.
    """
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
    """The student's one, whole-student attendance flag, or None.

    `grade_subject_offering_id=None` is the signal the rest of the system (the permission
    predicate, the router) reads to know this is not tied to one subject -- see the spec's
    Section 7.2 and `authorization/predicate.py`'s reuse in `service.py`.
    """
    if attendance_percent is None:
        return None
    driver = _attendance_level_driver(attendance_percent, thresholds)
    if driver is None:
        return None
    return EngineFlag(grade_subject_offering_id=None, tier=_tier_for((driver,)), drivers=(driver,))


def evaluate_student(
    signals: StudentSignals, thresholds: Thresholds = DEFAULT_THRESHOLDS
) -> list[EngineFlag]:
    """Every flag this student earns right now: zero or one per subject, plus zero or one
    for attendance. A student can legitimately end up with several -- one struggling
    subject and a fine attendance record produces exactly one flag; several struggling
    subjects produce several, each independently explainable. Nothing here caps the count
    or blends them into one "how at-risk is this child" composite -- that composite is
    exactly what Section 6.1 forbids, because it is what hides a single-subject problem
    inside a merely-below-average score.
    """
    flags = [evaluate_subject(subject, thresholds) for subject in signals.subjects]
    flags.append(evaluate_attendance(signals.attendance_percent, thresholds))
    return [flag for flag in flags if flag is not None]

"""The rule engine, tested with no database at all.

Every case here is either a real number pulled from the live synthetic school (labelled
as such) or a deliberately constructed edge case chosen to isolate one behaviour. Real
numbers prove the calibration described in engine.py's module docstring; constructed
cases prove the *rule* is right independent of whatever the data happens to look like
today.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from education_platform.modules.at_risk.engine import (
    EngineFlag,
    StudentSignals,
    SubjectSignal,
    Thresholds,
    evaluate_attendance,
    evaluate_student,
    evaluate_subject,
)

MATHS = uuid4()
SCIENCE = uuid4()

DEFAULT = Thresholds()


def _fine_subject(offering: UUID = MATHS) -> SubjectSignal:
    """A subject with nothing wrong: comfortably above the level threshold and flat."""
    return SubjectSignal(
        grade_subject_offering_id=offering,
        mastery_percent=82.0,
        attempt_scores_recent_first=(80.0, 82.0, 81.0, 83.0, 80.0),
    )


def test_a_student_above_every_threshold_gets_no_flag_at_all() -> None:
    """T-AR-04. Nothing wrong, nothing raised."""
    signals = StudentSignals(
        student_id=uuid4(), attendance_percent=94.0, subjects=(_fine_subject(),)
    )
    assert evaluate_student(signals) == []


def test_low_mastery_level_alone_is_a_monitor_tier_flag() -> None:
    """A flat, low score with no attempt history to compare against: one driver, the
    mildest tier."""
    subject = SubjectSignal(grade_subject_offering_id=MATHS, mastery_percent=55.0)
    flag = evaluate_subject(subject)
    assert flag is not None
    assert flag.tier == "monitor"
    assert [d.metric for d in flag.drivers] == ["mastery_percent"]
    assert flag.drivers[0].comparison == "below 60.0"


def test_declining_trend_alone_is_an_attention_tier_flag() -> None:
    """The case that proves trend checking is necessary on its own: a score still
    comfortably above the level line, but sliding hard. Level alone would clear this
    student; trend must not."""
    subject = SubjectSignal(
        grade_subject_offering_id=MATHS,
        mastery_percent=75.0,  # well above the 60.0 level threshold
        attempt_scores_recent_first=(60.0, 65.0, 68.0, 88.0, 90.0),  # recent first
    )
    flag = evaluate_subject(subject)
    assert flag is not None
    assert flag.tier == "attention"
    assert [d.metric for d in flag.drivers] == ["mastery_trend"]


def test_aishas_real_mathematics_sequence_produces_urgent_with_both_drivers() -> None:
    """Real data, not constructed: Aisha Rahman (S-00097), Mathematics, read from the
    live database 29 Aug 2026. Chronological scores were 74, 65, 56, 47, 38 -- so
    recent-first is the reverse. Her aggregate mastery (56%) is itself below the level
    threshold *and* her trend has declined past it: both drivers fire, independently,
    and the flag must name Mathematics specifically -- the exact requirement in the
    spec's Section 6.3."""
    subject = SubjectSignal(
        grade_subject_offering_id=MATHS,
        mastery_percent=56.0,
        attempt_scores_recent_first=(38.0, 47.0, 56.0, 65.0, 74.0),
    )
    flag = evaluate_subject(subject)
    assert flag is not None
    assert flag.grade_subject_offering_id == MATHS
    assert flag.tier == "urgent"
    metrics = {d.metric for d in flag.drivers}
    assert metrics == {"mastery_percent", "mastery_trend"}
    trend_driver = next(d for d in flag.drivers if d.metric == "mastery_trend")
    assert trend_driver.value == pytest.approx(22.5, abs=0.1)


def test_a_strong_subject_is_never_flagged_even_when_another_subject_of_the_same_student_is() -> (
    None
):
    """The core requirement doc 08 exists to guarantee: a subject-specific problem must
    not read as a globally struggling student. Science must produce nothing at all."""
    weak_maths = SubjectSignal(grade_subject_offering_id=MATHS, mastery_percent=56.0)
    fine_science = _fine_subject(SCIENCE)
    signals = StudentSignals(
        student_id=uuid4(), attendance_percent=95.0, subjects=(weak_maths, fine_science)
    )

    flags = evaluate_student(signals)

    assert len(flags) == 1
    assert flags[0].grade_subject_offering_id == MATHS


def test_multiple_struggling_subjects_produce_multiple_independent_flags() -> None:
    """Not capped, and not merged into one composite -- each is its own explainable flag."""
    weak_maths = SubjectSignal(grade_subject_offering_id=MATHS, mastery_percent=50.0)
    weak_science = SubjectSignal(grade_subject_offering_id=SCIENCE, mastery_percent=52.0)
    signals = StudentSignals(
        student_id=uuid4(), attendance_percent=95.0, subjects=(weak_maths, weak_science)
    )

    flags = evaluate_student(signals)

    assert {f.grade_subject_offering_id for f in flags} == {MATHS, SCIENCE}
    assert all(f.tier == "monitor" for f in flags)


def test_attendance_only_case_flags_attendance_without_any_subject_flag() -> None:
    """The synthetic school's planted counter-example shape: low attendance (70%, at the
    real cluster this project's data shows), strong marks everywhere -- proving
    attendance alone can raise a flag, and that a fine subject does not also fire."""
    signals = StudentSignals(
        student_id=uuid4(),
        attendance_percent=70.0,
        subjects=(_fine_subject(MATHS), _fine_subject(SCIENCE)),
    )

    flags = evaluate_student(signals)

    assert len(flags) == 1
    flag = flags[0]
    assert flag.grade_subject_offering_id is None
    assert [d.metric for d in flag.drivers] == ["attendance_percent"]
    assert flag.tier == "monitor"  # no attendance trend in this version -- see engine.py


def test_attendance_alone_never_explains_a_subject_flag() -> None:
    """The inverse of the above: bad attendance must not leak into a subject's own flag
    as an extra driver -- the two are evaluated, and reported, completely separately."""
    signals = StudentSignals(
        student_id=uuid4(),
        attendance_percent=65.0,
        subjects=(SubjectSignal(grade_subject_offering_id=MATHS, mastery_percent=50.0),),
    )

    flags = evaluate_student(signals)

    assert len(flags) == 2
    subject_flag = next(f for f in flags if f.grade_subject_offering_id == MATHS)
    attendance_flag = next(f for f in flags if f.grade_subject_offering_id is None)
    assert [d.metric for d in subject_flag.drivers] == ["mastery_percent"]
    assert [d.metric for d in attendance_flag.drivers] == ["attendance_percent"]


def test_a_new_student_with_too_little_history_does_not_trigger_a_trend_driver() -> None:
    """One prior attempt is not a baseline. The correct answer is silence, not a guess --
    and specifically not an error either; a new student is an ordinary case, not a bug."""
    subject = SubjectSignal(
        grade_subject_offering_id=MATHS,
        mastery_percent=90.0,
        attempt_scores_recent_first=(60.0, 95.0),  # looks like a huge "decline" naively
    )
    flag = evaluate_subject(subject)
    assert flag is None


def test_no_attempt_history_at_all_only_checks_level() -> None:
    """A subject with a mastery figure but zero recorded attempts (e.g. carried over from
    a prior period) still gets a level check; it simply cannot get a trend one."""
    subject = SubjectSignal(grade_subject_offering_id=MATHS, mastery_percent=40.0)
    flag = evaluate_subject(subject)
    assert flag is not None
    assert [d.metric for d in flag.drivers] == ["mastery_percent"]


def test_mastery_exactly_at_the_threshold_does_not_flag() -> None:
    """>= the line is fine; only strictly below it is a concern. The boundary itself must
    not be a coin flip between implementations."""
    subject = SubjectSignal(grade_subject_offering_id=MATHS, mastery_percent=60.0)
    assert evaluate_subject(subject) is None


def test_decline_exactly_at_the_threshold_does_not_flag() -> None:
    """Same boundary rule for the trend condition: a decline of exactly the threshold is
    not yet "past" it. Five scores, so there really are 2+ earlier attempts to compare
    against -- with fewer, this would pass for the wrong reason (not enough history to
    judge at all, tested separately above)."""
    subject = SubjectSignal(
        grade_subject_offering_id=MATHS,
        mastery_percent=90.0,
        # recent (first 3) avg 70.0, earlier (last 2) avg 85.0 -> exactly a 15.0 decline
        attempt_scores_recent_first=(70.0, 70.0, 70.0, 85.0, 85.0),
    )
    assert evaluate_subject(subject) is None


def test_attendance_exactly_at_the_threshold_does_not_flag() -> None:
    assert evaluate_attendance(80.0) is None


def test_attendance_of_none_produces_no_flag_rather_than_an_error() -> None:
    """A student with no attendance data yet (e.g. mid-enrolment) must not crash the
    engine or be treated as a concern by default."""
    assert evaluate_attendance(None) is None


def test_a_flag_cannot_be_constructed_with_no_drivers() -> None:
    """AR-1, enforced at the type level: there is no code path that produces a driver-
    less flag, because the type itself refuses to exist."""
    with pytest.raises(ValueError, match="AR-1"):
        EngineFlag(grade_subject_offering_id=MATHS, tier="monitor", drivers=())


def test_custom_thresholds_change_the_outcome() -> None:
    """Recalibration is a matter of passing different data, not editing the rule -- this
    is the whole point of `Thresholds` being a parameter and not a constant baked into
    the comparison logic."""
    subject = SubjectSignal(grade_subject_offering_id=MATHS, mastery_percent=65.0)

    assert evaluate_subject(subject, DEFAULT) is None  # 65 >= default 60.0

    stricter = Thresholds(mastery_level=70.0)
    flag = evaluate_subject(subject, stricter)
    assert flag is not None
    assert flag.drivers[0].comparison == "below 70.0"


def test_a_weak_section_produces_ordinary_independent_flags_not_a_cohort_object() -> None:
    """Spec Section 6.3's fourth named case: a whole section trending weak (e.g. a
    teaching gap) must not be silently hidden, but this engine also must not invent a
    cohort-level concept it was not designed for. Evaluating several individually-weak
    students produces exactly that many ordinary per-student flags -- nothing more,
    nothing aggregated -- which is the honest limit of what this version claims to do."""
    flags: list[EngineFlag] = []
    for _ in range(5):
        signals = StudentSignals(
            student_id=uuid4(),
            attendance_percent=95.0,
            subjects=(SubjectSignal(grade_subject_offering_id=MATHS, mastery_percent=52.0),),
        )
        flags.extend(evaluate_student(signals))

    assert len(flags) == 5
    assert all(f.grade_subject_offering_id == MATHS for f in flags)
    assert all(len(f.drivers) == 1 for f in flags)

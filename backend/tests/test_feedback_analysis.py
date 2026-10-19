"""Level-specific feedback analysis: wording, links, and the model guard."""

from dataclasses import replace
from decimal import Decimal

from education_platform.modules.assessments.feedback_analysis import (
    ConceptFact,
    GoalFact,
    OverviewContext,
    ScoredItem,
    StudyLink,
    SubjectContext,
    TopicContext,
    accept_model_text,
    overview_analysis,
    subject_analysis,
    topic_analysis,
)

_LESSON = """# Decimals

## Slide 1 — This topic

What decimals are.

## Slide 2 — Ideas in this topic

- Place value
- Comparing decimals
- Adding and subtracting decimals
"""

_HREF = "/subjects/math/topics/decimals/lesson"


def _concept(name: str, correct: int, answered: int) -> ConceptFact:
    percent = (Decimal(correct) / Decimal(answered) * Decimal("100")).quantize(Decimal("0.01"))
    return ConceptFact(name, correct, answered, percent)


def _topic() -> TopicContext:
    return TopicContext(
        topic_name="Decimals",
        concepts=(
            _concept("Comparing decimals", 0, 5),
            _concept("Adding and subtracting decimals", 2, 4),
            _concept("Place value", 4, 4),
        ),
        trend_delta=Decimal("-12"),
        goal_target=Decimal("80"),
        best_percent=Decimal("58"),
        confidence="confident",
        lesson_title="Decimals",
        lesson_href=_HREF,
        lesson_markdown=_LESSON,
        extra_links=(),
        forbidden_names=("Fractions", "Ratios"),
    )


def test_topic_template_names_weak_concepts_and_only_real_links() -> None:
    draft = topic_analysis(_topic())
    assert "Comparing decimals (0 of 5 correct)" in draft.text
    assert "Adding and subtracting decimals (2 of 4 correct)" in draft.text
    assert "Place value (" not in draft.text
    assert f"[Decimals]({_HREF})" in draft.text
    assert "Slide 2 — Ideas in this topic" in draft.text
    assert f"{_HREF}?slide=2" in draft.text
    assert "?slide=1" not in draft.text
    assert draft.text.count("?slide=2") == 1
    assert "22 points remain" in draft.text
    assert "You said Confident, but 1 concept is under 30%; worth a review." in draft.text
    assert "Fractions" not in draft.text
    assert "http://" not in draft.text
    kept, used_model = accept_model_text(draft.text, "template", draft.prompt)
    assert used_model is True
    assert kept == draft.text


def test_topic_template_omits_links_when_nothing_is_published() -> None:
    draft = topic_analysis(
        replace(
            _topic(),
            lesson_title=None,
            lesson_href=None,
            lesson_markdown=None,
            goal_target=None,
            confidence=None,
            trend_delta=None,
        )
    )
    assert "Concentrate on" in draft.text
    assert "/lesson" not in draft.text
    assert "http" not in draft.text
    assert "goal" not in draft.text.lower()
    assert "You said" not in draft.text


def test_topic_slide_link_is_omitted_when_the_name_is_not_in_the_lesson() -> None:
    draft = topic_analysis(
        replace(
            _topic(),
            concepts=(_concept("Solid shapes", 0, 5),),
            confidence=None,
            goal_target=None,
        )
    )
    assert "Solid shapes (0 of 5 correct)" in draft.text
    assert f"[Decimals]({_HREF})" in draft.text
    assert "?slide=" not in draft.text


def test_subject_template_stays_on_topics() -> None:
    draft = subject_analysis(
        SubjectContext(
            subject_name="Mathematics",
            topics=(
                ScoredItem("Decimals", Decimal("85"), Decimal("-65")),
                ScoredItem("Percentages", Decimal("76")),
                ScoredItem("Algebra", Decimal("74")),
                ScoredItem("Ratios", Decimal("62")),
                ScoredItem("Fractions", Decimal("58")),
                ScoredItem("Mensuration", None),
            ),
            trend_delta=Decimal("-65.09"),
            confidence="confident",
            goals=(GoalFact("Fractions", Decimal("80"), 22),),
            forbidden_names=("Place value", "Comparing decimals", "Cuboid"),
        )
    )
    assert (
        draft.text == "Decimals, Percentages, and Algebra are going well; "
        "focus next on Fractions and Ratios. "
        "Scores are down 65 points across topics since the previous attempts. "
        "You said Confident, but Fractions and Ratios are under 70%."
    )
    for banned in ("Place value", "Comparing decimals", "Cuboid", "Mensuration"):
        assert banned not in draft.text
    assert "/lesson" not in draft.text
    assert "goals" in draft.prompt


def test_overview_template_stays_on_subjects() -> None:
    draft = overview_analysis(
        OverviewContext(
            subjects=(
                ScoredItem("Social Studies", Decimal("85"), None),
                ScoredItem("Arabic", Decimal("77"), None),
                ScoredItem("Mathematics", Decimal("71"), Decimal("-65")),
                ScoredItem("Science", Decimal("67"), None),
                ScoredItem("English", Decimal("62"), None),
            ),
            ratings=(
                ("Mathematics", "confident", Decimal("71")),
                ("English", "still_learning", Decimal("62")),
                ("Science", None, Decimal("67")),
            ),
            forbidden_names=("Fractions", "Decimals", "Algebra", "Place value"),
        )
    )
    assert draft.text.startswith(
        "Social Studies, Arabic, and Mathematics are going well; "
        "English and Science are where to focus."
    )
    assert "Scores are down 65 points across subjects" in draft.text
    for banned in ("Fractions", "Decimals", "Algebra", "Place value"):
        assert banned not in draft.text
    assert "You said Confident in Mathematics" not in draft.text
    assert "/subjects/" not in draft.text


def test_overview_calibration_names_the_subject_when_the_rating_disagrees() -> None:
    draft = overview_analysis(
        OverviewContext(
            subjects=(
                ScoredItem("Mathematics", Decimal("58")),
                ScoredItem("Science", Decimal("88")),
            ),
            ratings=(
                ("Mathematics", "confident", Decimal("58")),
                ("Science", "still_learning", Decimal("88")),
            ),
            forbidden_names=("Algebra",),
        )
    )
    assert "You said Confident in Mathematics, but that subject is under 70%." in draft.text
    assert "You said Still learning in Science, but that subject is at 88%." in draft.text
    assert "Algebra" not in draft.text


def test_model_text_that_names_the_wrong_level_or_an_unknown_link_is_dropped() -> None:
    draft = subject_analysis(
        SubjectContext(
            subject_name="Mathematics",
            topics=(ScoredItem("Fractions", Decimal("80")),),
            trend_delta=None,
            confidence=None,
            goals=(),
            forbidden_names=("Cuboid",),
        )
    )
    leaked, used_leak = accept_model_text(
        "Fractions is going well, especially Cuboid.",
        draft.text,
        draft.prompt,
    )
    assert used_leak is False
    assert leaked == draft.text
    assert "Cuboid" not in leaked

    topic = topic_analysis(replace(_topic(), confidence=None, goal_target=None, trend_delta=None))
    linked, used_link = accept_model_text(
        f"Review [Extra]({_HREF}/made-up).",
        topic.text,
        topic.prompt,
    )
    assert used_link is False
    assert linked == topic.text
    assert "made-up" not in linked


def test_empty_model_text_and_a_legacy_prompt_follow_todays_rules() -> None:
    template = "Fractions is going well."
    fallback, used_model = accept_model_text("", template, "no guard here")
    assert used_model is False
    assert fallback == template

    kept, used_legacy = accept_model_text("Generated once.", template, "old dashboard prompt")
    assert used_legacy is True
    assert kept == "Generated once."

    broken, used_broken = accept_model_text("Looks fine.", template, "ANALYSIS_GUARD\nnot-json")
    assert used_broken is False
    assert broken == template


def test_extra_published_lesson_is_included_and_not_invented() -> None:
    extra = StudyLink("Place value notes", "/subjects/math/subtopics/place/lesson")
    draft = topic_analysis(
        replace(_topic(), extra_links=(extra,), confidence=None, goal_target=None)
    )
    assert "[Place value notes](/subjects/math/subtopics/place/lesson)" in draft.text
    invented, used_model = accept_model_text(
        "See [Workbook](/subjects/math/topics/decimals/workbook).",
        draft.text,
        draft.prompt,
    )
    assert used_model is False
    assert invented == draft.text

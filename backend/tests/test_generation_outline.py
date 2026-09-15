"""Largest Remainder and outline helpers."""

from decimal import Decimal
from uuid import uuid4

import pytest

from education_platform.modules.generation.outline import (
    assert_dag,
    combined_weight,
    largest_remainder,
    outline_from_headings,
    parse_proposed_outline,
)
from education_platform.modules.generation.types import HeadingCluster, OutlineNodeEdit


def test_largest_remainder_unit_weights() -> None:
    quotas = largest_remainder(
        (Decimal("0.46"), Decimal("0.33"), Decimal("0.21")),
        80,
    )
    assert quotas == (37, 26, 17)


def test_largest_remainder_tie_breaks_original_order() -> None:
    quotas = largest_remainder(
        (Decimal("0.8"), Decimal("0.4"), Decimal("0.8")),
        2,
    )
    assert quotas == (1, 0, 1)


def test_largest_remainder_rejects_all_zero_weights() -> None:
    with pytest.raises(ValueError, match="all-zero"):
        largest_remainder((Decimal("0"), Decimal("0")), 80)


def test_combined_weight_blends_equally() -> None:
    assert combined_weight(
        token_mass=3,
        prerequisite_score=Decimal("0.5"),
        centrality=Decimal("0.5"),
    ) == Decimal("4") / Decimal("3")


def test_outline_from_headings_is_flat() -> None:
    outline = outline_from_headings(
        (
            HeadingCluster(heading="Squares", token_mass=10, sample_texts=("a",)),
            HeadingCluster(heading="Triangles", token_mass=4, sample_texts=("b",)),
        )
    )
    assert len(outline.nodes) == 2
    assert outline.nodes[0].parent_key is None
    assert outline.nodes[0].prerequisite_score == Decimal("0.5")
    assert outline.nodes[0].slug == "squares"


def test_parse_proposed_outline_rejects_half_graphs() -> None:
    with pytest.raises(ValueError, match="nodes"):
        parse_proposed_outline({"nodes": []})
    with pytest.raises(ValueError, match="parent_key"):
        parse_proposed_outline(
            {
                "nodes": [
                    {
                        "key": "a",
                        "parent_key": "missing",
                        "slug": "a",
                        "title": "A",
                        "token_mass": 1,
                        "prerequisite_score": 0.5,
                        "centrality": 0.5,
                        "proposed_outcomes": ["Know A"],
                    }
                ]
            }
        )


def test_assert_dag_rejects_unknown_parent_and_cycles() -> None:
    node_id = uuid4()
    other = uuid4()
    with pytest.raises(ValueError, match="unknown parent"):
        assert_dag(
            (
                OutlineNodeEdit(
                    id=node_id,
                    parent_id=other,
                    slug="a",
                    title="A",
                    weight=Decimal("1"),
                    matched_subtopic_id=None,
                    force_create=False,
                    proposed_outcomes=("Know A",),
                    sequence=1,
                ),
            )
        )
    with pytest.raises(ValueError, match="cycle"):
        a = uuid4()
        b = uuid4()
        assert_dag(
            (
                OutlineNodeEdit(
                    id=a,
                    parent_id=b,
                    slug="a",
                    title="A",
                    weight=Decimal("1"),
                    matched_subtopic_id=None,
                    force_create=False,
                    proposed_outcomes=("Know A",),
                    sequence=1,
                ),
                OutlineNodeEdit(
                    id=b,
                    parent_id=a,
                    slug="b",
                    title="B",
                    weight=Decimal("1"),
                    matched_subtopic_id=None,
                    force_create=False,
                    proposed_outcomes=("Know B",),
                    sequence=2,
                ),
            )
        )

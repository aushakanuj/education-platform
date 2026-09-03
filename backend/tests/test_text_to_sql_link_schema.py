"""Tests for link_schema.py — the per-question schema-narrowing node between
load_schema and generate_sql.

Structured in three tiers:

1. Unit tests against the parsing/matching primitives directly (fast, no I/O).
2. A self-contained recall regression test with ground-truth (question, expected
   tables) pairs baked in as literal data — these are the exact patterns this node's
   tuning history (see link_schema.py's module docstring) was fixed against, so they
   must never regress, in any environment, with no external file dependency.
3. A full real-data recall test against every golden-eval question that has a real
   recorded validated_sql, read from the actual Excel workbook maintained alongside
   this project. That file is untracked in git (a local, human-maintained evaluation
   artifact — confirmed via `git status`), so this tier skips gracefully when it's
   absent rather than failing the suite in an environment that doesn't have it, the
   same posture test_text_to_sql_generate_sql_live.py uses for RUN_LIVE_LLM_TESTS.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from education_platform.modules.text_to_sql.nodes.link_schema import (
    _parse_fk_graph,
    _parse_table_blocks,
    _select_tables,
    _table_vocabulary,
    _words,
    link_schema,
)
from education_platform.modules.text_to_sql.nodes.load_schema import (
    REQUIRED_TABLES,
    _load_filtered_schema_context,
)

_GOLDEN_EVAL_XLSX = (
    Path(__file__).resolve().parent.parent.parent
    / "Text-to-SQL-Golden-Eval-Set-50_Set-2.xlsx"
)


def _full_schema_context() -> str:
    return _load_filtered_schema_context()


# --- Tier 1: unit tests against the primitives ---------------------------------------


def test_words_lowercases_and_adds_naive_singular() -> None:
    words = _words("Teachers ASSIGNED to Sections")
    assert "teachers" in words
    assert "teacher" in words  # naive trailing-s strip
    assert "sections" in words
    assert "section" in words


def test_words_drops_short_fragments() -> None:
    words = _words("id at is a to")
    assert words == set()


def test_table_vocabulary_excludes_fk_columns() -> None:
    ctx = _full_schema_context()
    blocks = _parse_table_blocks(ctx)
    vocab = _table_vocabulary("teaching_assignments", blocks["teaching_assignments"])
    # "grade" only appears here via FK columns (grade_subject_offering_id) -- must not
    # be present; this is the exact bug this design fixed (see module docstring).
    assert "grade" not in vocab
    # Non-FK words (table name parts, status) must still be present.
    assert "teaching" in vocab
    assert "assignments" in vocab
    assert "status" in vocab


def test_fk_graph_connects_period_grades_to_both_neighbors() -> None:
    ctx = _full_schema_context()
    graph = _parse_fk_graph(ctx)
    assert "period_grades" in graph["grades"]
    assert "period_grades" in graph["grade_subject_offerings"]
    # Undirected: the reverse direction must also be present.
    assert "grades" in graph["period_grades"]
    assert "grade_subject_offerings" in graph["period_grades"]


def test_select_tables_closure_reaches_unnamed_intermediate_table() -> None:
    # The exact row-45/46 pattern this node exists to avoid repeating: "period" is never
    # said, but the join needs period_grades between grades and grade_subject_offerings.
    ctx = _full_schema_context()
    selected = _select_tables(
        "What topics are covered in the Grade 8 Science curriculum?", ctx
    )
    assert selected is not None
    assert "period_grades" in selected
    assert "topics" in selected
    assert "grades" in selected


def test_select_tables_always_included_present_regardless_of_wording() -> None:
    ctx = _full_schema_context()
    # A question with zero lexical connection to teaching/periods/subjects.
    selected = _select_tables("List all institutions.", ctx)
    assert selected is not None
    # student_360 lives in §5, never a §2 table block, so it's deliberately excluded
    # from the *returned* selection (guards against a typo'd always-included name that
    # isn't a real §2 table) — but §5 itself is never touched by narrowing regardless,
    # so its content survives either way (see the narrowing-preserves-§5 test below).
    # This test only covers the two always-included names that *are* real §2 blocks.
    assert {"teaching_assignments", "academic_periods", "subjects"} <= selected
    assert "student_360" not in _parse_table_blocks(ctx)


def test_select_tables_returns_none_on_zero_lexical_overlap() -> None:
    ctx = _full_schema_context()
    # Every word here is either a stopword-length fragment or matches nothing in the
    # schema's table/column vocabulary at all.
    selected = _select_tables("xyzzy plugh", ctx)
    assert selected is None


def test_narrows_to_a_real_fraction_of_the_full_table_count() -> None:
    ctx = _full_schema_context()
    selected = _select_tables("What subject do I teach?", ctx)
    assert selected is not None
    # Real narrowing happened -- not everything, and not nothing.
    total_tables = len(_parse_table_blocks(ctx))
    assert 0 < len(selected) < total_tables


# --- Tier 1b: the node function itself -------------------------------------------------


async def test_link_schema_narrows_and_records_selection_in_audit_entry() -> None:
    ctx = _full_schema_context()
    state = {
        "question": "What subject do I teach?",
        "schema_context": ctx,
        "user_id": "x",
        "user_role": "teacher",
        "institution_id": "i",
        "error": None,
        "retry_count": 0,
        "audit_entry": None,
    }
    result = await link_schema(state)
    assert result["schema_context"] != ctx
    assert len(result["schema_context"]) < len(ctx)
    selected = result["audit_entry"]["schema_linking_tables_selected"]
    assert selected is not None
    assert "teaching_assignments" in selected


async def test_link_schema_preserves_always_kept_sections_verbatim() -> None:
    ctx = _full_schema_context()
    state = {
        "question": "What subject do I teach?",
        "schema_context": ctx,
        "user_id": "x",
        "user_role": "teacher",
        "institution_id": "i",
        "error": None,
        "retry_count": 0,
        "audit_entry": None,
    }
    result = await link_schema(state)
    narrowed = result["schema_context"]
    conventions_start = ctx.index("## 1. Conventions")
    conventions_end = ctx.index("## 2. Table Catalog")
    assert ctx[conventions_start:conventions_end] in narrowed
    student_360_start = ctx.index("## 5. Derived View")
    student_360_end = ctx.index("## 6. Glossary")
    assert ctx[student_360_start:student_360_end] in narrowed
    glossary_start = ctx.index("## 6. Glossary")
    assert ctx[glossary_start:] in narrowed


async def test_link_schema_fallback_returns_original_context_on_no_match() -> None:
    ctx = _full_schema_context()
    state = {
        "question": "xyzzy plugh",
        "schema_context": ctx,
        "user_id": "x",
        "user_role": "teacher",
        "institution_id": "i",
        "error": None,
        "retry_count": 0,
        "audit_entry": None,
    }
    result = await link_schema(state)
    assert result["schema_context"] == ctx
    assert result["audit_entry"]["schema_linking_tables_selected"] is None


async def test_link_schema_never_reads_identity_fields() -> None:
    # Structural proof, not just a docstring claim: patch user_id/user_role/
    # institution_id to values that would break anything reading them, and confirm the
    # result is identical to a run with normal values -- same technique
    # test_only_reads_user_id_and_user_role uses for apply_role_scope.
    ctx = _full_schema_context()
    base_state = {
        "question": "What subject do I teach?",
        "schema_context": ctx,
        "error": None,
        "retry_count": 0,
        "audit_entry": None,
    }
    result_a = await link_schema({**base_state, "user_id": "a", "user_role": "teacher", "institution_id": "i1"})
    result_b = await link_schema(
        {**base_state, "user_id": None, "user_role": None, "institution_id": None}
    )
    assert result_a["schema_context"] == result_b["schema_context"]


# --- Tier 2: self-contained recall regression (no external file) ---------------------

# (question, tables the real system needs for it) -- exact patterns link_schema.py's
# tuning history was fixed against. If any of these regress, the fix that made them
# pass has been undone.
_GROUND_TRUTH_CASES: tuple[tuple[str, frozenset[str]], ...] = (
    ("How many students do I teach in total?", frozenset({"teaching_assignments"})),
    (
        "What is the average attendance rate for my students this term?",
        frozenset({"academic_periods", "attendance_records"}),
    ),
    (
        "What is the average mastery score for my students in Mathematics?",
        frozenset({"subjects", "common_mastery_quizzes"}),
    ),
    (
        "Who are my top 5 highest-scoring students in Science?",
        frozenset({"subjects", "teaching_assignments"}),
    ),
    (
        "What topics are covered in the Grade 8 Science curriculum?",
        frozenset({"period_grades", "grade_subject_offerings", "subjects", "topics"}),
    ),
)


@pytest.mark.parametrize("question,expected_tables", _GROUND_TRUTH_CASES)
def test_ground_truth_recall_regression(
    question: str, expected_tables: frozenset[str]
) -> None:
    ctx = _full_schema_context()
    selected = _select_tables(question, ctx)
    assert selected is not None
    missing = expected_tables - selected
    assert not missing, f"{question!r} is missing {missing} -- a false negative regression"


# --- Tier 3: full real-data recall against the golden eval set (skips if absent) -----


def _real_tables_referenced(sql: str) -> set[str]:
    import re

    sql_lower = sql.lower()
    return {t for t in REQUIRED_TABLES if re.search(rf"\b{re.escape(t)}\b", sql_lower)}


@pytest.mark.skipif(
    not _GOLDEN_EVAL_XLSX.exists(),
    reason=f"golden eval workbook not present at {_GOLDEN_EVAL_XLSX} (untracked, "
    "local-only artifact) -- run on a checkout that has it to re-validate recall "
    "against the full real question set",
)
def test_zero_false_negatives_against_full_golden_eval_set() -> None:
    import openpyxl

    wb = openpyxl.load_workbook(_GOLDEN_EVAL_XLSX, data_only=True)
    ws = wb["Eval Questions"]
    ctx = _full_schema_context()

    checked = 0
    failures: list[str] = []
    for row in ws.iter_rows(min_row=3, values_only=True):
        qid, question, validated_sql = row[0], row[3], row[11]
        if qid is None or not question or not validated_sql:
            continue
        real_tables = _real_tables_referenced(validated_sql)
        if not real_tables:
            continue
        checked += 1
        selected = _select_tables(question, ctx)
        if selected is None:
            continue  # fallback = full context, cannot be a false negative
        missing = real_tables - selected - {"student_360"}
        if missing:
            failures.append(f"row {qid}: missing {missing} for {question!r}")

    assert checked >= 20, f"expected substantial real ground-truth coverage, got {checked}"
    assert not failures, "false negatives against real golden-eval data:\n" + "\n".join(failures)

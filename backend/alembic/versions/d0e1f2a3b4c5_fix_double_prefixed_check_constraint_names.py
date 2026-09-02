"""Fix double-prefixed CHECK constraint names project-wide.

Root cause (see `education_platform.db.base.metadata`'s `naming_convention`): its `"ck"`
entry, `"ck_%(table_name)s_%(constraint_name)s"`, expects callers to pass only the
unprefixed suffix (`name="attempt_number"`) so the convention can build the full name
itself. Every `CheckConstraint(...)` declared inline inside an `op.create_table(...)` /
ORM `__table_args__` across this project's history instead passes the *already-complete*
name (`name="ck_quiz_attempts_attempt_number"`) — SQLAlchemy still substitutes that
complete string into `%(constraint_name)s` and prepends `ck_%(table_name)s_` on top
regardless, producing `ck_quiz_attempts_ck_quiz_attempts_attempt_number`. Confirmed
empirically (not assumed): reproducing both the buggy and the intended call shape against
a throwaway `MetaData` with this project's exact naming_convention shows the short-suffix
form resolves correctly and the complete-name form double-prefixes every time.

This is why `chunk_embeddings.doc_kind` and `ingest_jobs.exactly_one_target` already carry
correct names (see migrations `a7b8c9d0e1f2`/`b9c0d1e2f3a4`): both used the *other*
project idiom, `op.drop_constraint("<suffix>", table, type_="check")` /
`op.create_check_constraint("<suffix>", table, sql)`, which already takes the unprefixed
suffix and was never affected. Every other named CHECK constraint in the schema — added
via a raw `CheckConstraint(name="ck_...")` inside `op.create_table(...)` — has the bug.
Postgres additionally hash-truncates any resulting name over 63 bytes, so five of these
carry a truncated, hashed tail rather than a clean double-prefix; the mapping below is
built from a live `pg_constraint` query and cross-checked against each constraint's
`pg_get_constraintdef()` output against the ORM model's own source `CheckConstraint` call,
not inferred from the doubling pattern alone (the two truncated `student_material_progress`
entries in particular resolve to different target names and are only distinguishable by
their actual CHECK clause, not their name).

Rename mechanism: `ALTER TABLE ... RENAME CONSTRAINT ... TO ...`, not this project's other
established idiom (`op.drop_constraint` + `op.create_check_constraint`, as the two
migrations above used). That pairing is the right tool when the constraint's *definition*
is also changing (as it was for `chunk_embeddings.doc_kind`'s vocabulary migration) — drop
and recreate, even inside one transaction, makes Postgres re-validate the check against
every existing row. Here the check text is not changing at all, only its catalog name;
`RENAME CONSTRAINT` is a pure `pg_constraint` metadata update with no table scan and no
re-validation, confirmed directly against this database (timed manually against
`quiz_attempts`, and confirmed a violating insert was still correctly rejected under the
renamed constraint immediately afterward, then reverted before writing this migration).
For 19 constraints, some on tables that could hold meaningfully more rows than this dev
database does, the cheaper primitive is the right default, not just the available one.

Root cause fixed separately, in the same change: `education_platform.db.base.metadata`'s
naming_convention no longer includes a `"ck"` entry at all (see that module). Every
existing call site across models and migrations already passes a complete, already-correct
name — removing the entry stops SQLAlchemy from re-templating it a second time, for every
CHECK constraint this project will ever declare the same way again, not just the 19 fixed
here. This is a schema-neutral source change (it only affects what name a *future*
`CheckConstraint(name=...)` call resolves to before it is ever sent to a database) and
needs no migration of its own.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-09-02 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str | Sequence[str] | None = "d0e1f2a3b4c5"
down_revision: str | Sequence[str] | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, current double-prefixed/truncated name in the live schema, correct name matching
# the ORM model's own `CheckConstraint(name=...)` source). Built from a live `pg_constraint`
# query against this project's own database, cross-checked constraint-by-constraint against
# `pg_get_constraintdef()` and the matching model source line -- not inferred from the
# doubling pattern alone, which is not reliable once Postgres has hash-truncated a name.
_RENAMES: tuple[tuple[str, str, str], ...] = (
    (
        "common_mastery_quizzes",
        "ck_common_mastery_quizzes_ck_common_mastery_quizzes_exa_29cb",
        "ck_common_mastery_quizzes_exactly_one_target",
    ),
    (
        "knowledge_chunks",
        "ck_knowledge_chunks_ck_knowledge_chunks_ordinal",
        "ck_knowledge_chunks_ordinal",
    ),
    (
        "knowledge_chunks",
        "ck_knowledge_chunks_ck_knowledge_chunks_token_count",
        "ck_knowledge_chunks_token_count",
    ),
    (
        "knowledge_document_versions",
        "ck_knowledge_document_versions_ck_knowledge_document_ve_06e1",
        "ck_knowledge_document_versions_version_number",
    ),
    (
        "question_versions",
        "ck_question_versions_ck_question_versions_marks",
        "ck_question_versions_marks",
    ),
    (
        "question_versions",
        "ck_question_versions_ck_question_versions_version_number",
        "ck_question_versions_version_number",
    ),
    (
        "quiz_attempts",
        "ck_quiz_attempts_ck_quiz_attempts_attempt_number",
        "ck_quiz_attempts_attempt_number",
    ),
    (
        "quiz_attempts",
        "ck_quiz_attempts_ck_quiz_attempts_pass_threshold",
        "ck_quiz_attempts_pass_threshold",
    ),
    (
        "quiz_attempts",
        "ck_quiz_attempts_ck_quiz_attempts_score_percent",
        "ck_quiz_attempts_score_percent",
    ),
    (
        "quiz_items",
        "ck_quiz_items_ck_quiz_items_sequence",
        "ck_quiz_items_sequence",
    ),
    (
        "quiz_releases",
        "ck_quiz_releases_ck_quiz_releases_window_order",
        "ck_quiz_releases_window_order",
    ),
    (
        "quiz_versions",
        "ck_quiz_versions_ck_quiz_versions_duration_seconds",
        "ck_quiz_versions_duration_seconds",
    ),
    (
        "quiz_versions",
        "ck_quiz_versions_ck_quiz_versions_max_attempts",
        "ck_quiz_versions_max_attempts",
    ),
    (
        "quiz_versions",
        "ck_quiz_versions_ck_quiz_versions_version_number",
        "ck_quiz_versions_version_number",
    ),
    (
        "source_chunks",
        "ck_source_chunks_ck_source_chunks_ordinal",
        "ck_source_chunks_ordinal",
    ),
    (
        "source_chunks",
        "ck_source_chunks_ck_source_chunks_token_count",
        "ck_source_chunks_token_count",
    ),
    (
        "source_material_versions",
        "ck_source_material_versions_ck_source_material_versions_f04b",
        "ck_source_material_versions_version_number",
    ),
    (
        "student_material_progress",
        "ck_student_material_progress_ck_student_material_progre_2be0",
        "ck_student_material_progress_last_unit",
    ),
    (
        "student_material_progress",
        "ck_student_material_progress_ck_student_material_progre_6a51",
        "ck_student_material_progress_status_timestamps",
    ),
)


def upgrade() -> None:
    for table, old_name, new_name in _RENAMES:
        op.execute(f'ALTER TABLE {table} RENAME CONSTRAINT "{old_name}" TO "{new_name}"')


def downgrade() -> None:
    for table, old_name, new_name in _RENAMES:
        op.execute(f'ALTER TABLE {table} RENAME CONSTRAINT "{new_name}" TO "{old_name}"')

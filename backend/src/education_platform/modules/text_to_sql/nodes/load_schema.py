"""Entry node: loads a filtered `schema_context` from schema_catalog.md.

The `assistant` module (chat_conversations, chat_messages), the `rag` module
(knowledge_documents, knowledge_document_versions, knowledge_chunks, ingest_jobs,
chunk_embeddings), and the `audit_events` table (auth module) are out of scope for the
text-to-SQL assistant and must never reach the LLM as schema context — for any role,
under any circumstances.

This is enforced as a hard filter, not a prompt instruction: the excluded content is
structurally removed from the markdown before it is ever assigned to
`state["schema_context"]`, and a post-filter guard re-scans the result and refuses to
return it if any excluded table name survived. Read the catalog once (cached
thereafter, see `_load_filtered_schema_context`), not on every call.

Filtering approach, in order:
1. Structurally remove the `assistant` and `rag` `### Module: ...` sections of §2
   wholesale (every table under them is excluded).
2. Structurally remove just the `audit_events` table block from within the `auth`
   module section (its siblings — institutions, users, ... — are kept).
3. Rewrite the handful of genuinely general §1/§7 bullets that happen to *mention* an
   excluded table only incidentally (as an example), so their real, still-applicable
   point survives without the excluded name attached. This has to happen before step 4,
   or the blanket line-drop would delete these bullets outright along with everything
   else that mentions an excluded name.
4. Blanket-drop every remaining single line (table row, FK line, glossary row, gotcha
   bullet) that mentions an excluded table name — safe here because every remaining
   such line in this catalog is self-contained (see the module-level tests for the one
   case, a glossary row mixing an excluded and a kept table, where this deliberately
   drops the whole row rather than trying to save half of it).
5. Remove the "Polymorphic references" intro sentence in §4, which does not itself name
   an excluded table but is left pointing at an empty code fence once step 4 has run
   (every line inside that fence names one), and collapse any empty code fences and
   excess blank lines left behind by the removals above.
6. Validate: no excluded table name survives anywhere in the result, every table that
   *should* survive still does, and the result isn't suspiciously short or missing its
   top-level section headers. Any failure here means the filter itself broke (e.g.
   schema_catalog.md's structure changed) — fail loudly rather than ship a silently
   gutted or leaky context.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from education_platform.modules.text_to_sql.state import TextToSQLState

SCHEMA_CATALOG_PATH = Path(__file__).resolve().parent.parent / "schema_catalog.md"

# Tables that must never appear in schema_context, for any role, ever.
EXCLUDED_TABLES: tuple[str, ...] = (
    "chat_conversations",
    "chat_messages",
    "knowledge_documents",
    "knowledge_document_versions",
    "knowledge_chunks",
    "ingest_jobs",
    "chunk_embeddings",
    "audit_events",
)

# Tables/views that must survive filtering. If any go missing, the filter over-stripped
# (most likely schema_catalog.md's structure changed under it) and load_schema should
# fail rather than silently ship a gutted context.
REQUIRED_TABLES: tuple[str, ...] = (
    "institutions",
    "users",
    "user_roles",
    "student_profiles",
    "refresh_sessions",
    "grades",
    "subjects",
    "academic_periods",
    "period_grades",
    "sections",
    "grade_subject_offerings",
    "topics",
    "subtopics",
    "learning_outcomes",
    "student_grade_enrollments",
    "student_subject_enrollments",
    "teaching_assignments",
    "source_materials",
    "source_material_versions",
    "source_chunks",
    "student_material_progress",
    "questions",
    "question_versions",
    "question_options",
    "question_answer_keys",
    "question_outcome_tags",
    "common_mastery_quizzes",
    "quiz_versions",
    "quiz_items",
    "quiz_material_bindings",
    "quiz_releases",
    "quiz_attempts",
    "attempt_answers",
    "attendance_records",
    "student_360",
)

_MIN_LENGTH = 2000  # a real filtered catalog is tens of KB; anything this short is broken
_REQUIRED_HEADERS = (
    "## 1. Conventions",
    "## 2. Table Catalog",
    "## 3. Enum Reference",
    "## 4. Foreign Key Relationships",
    "## 5. Derived View",
    "## 6. Glossary",
    "## 7. Query Notes & Gotchas",
)


class SchemaCatalogError(Exception):
    """Raised when schema_catalog.md is missing, unreadable, or the filtered result is
    malformed (leaked excluded content, lost required content, or came out too short).
    """


def _excluded_pattern() -> re.Pattern[str]:
    return re.compile(r"\b(" + "|".join(re.escape(t) for t in EXCLUDED_TABLES) + r")\b")


def _remove_module_section(text: str, module_name: str) -> str:
    """Remove an entire `### Module: \\`name\\` ...` §2 subsection, header through its
    last table, up to (not including) the next `---` separator.
    """
    pattern = re.compile(
        rf"### Module: `{re.escape(module_name)}`.*?(?=\n---\n)",
        re.DOTALL,
    )
    new_text, count = pattern.subn("", text, count=1)
    if count != 1:
        raise SchemaCatalogError(
            f"expected exactly one '{module_name}' module section in schema_catalog.md, "
            f"found {count} — has the document structure changed?"
        )
    return new_text


def _remove_table_block(text: str, table_name: str) -> str:
    """Remove one `#### \\`table_name\\` ...` block, up to (not including) the next
    table header or module separator.
    """
    pattern = re.compile(
        rf"#### `{re.escape(table_name)}`\n.*?(?=\n#### |\n---\n)",
        re.DOTALL,
    )
    new_text, count = pattern.subn("", text, count=1)
    if count != 1:
        raise SchemaCatalogError(
            f"expected exactly one '{table_name}' table block in schema_catalog.md, "
            f"found {count} — has the document structure changed?"
        )
    return new_text


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    """`str.replace`, but fails loudly if `old` isn't found exactly once — a silent
    no-op here would mean a bullet meant to be scrubbed of excluded-table names instead
    survives untouched into the blanket line-drop and gets deleted outright, quietly
    losing genuinely general content.
    """
    count = text.count(old)
    if count != 1:
        raise SchemaCatalogError(
            f"expected to find {label} exactly once in schema_catalog.md, found {count} "
            "— has the wording changed?"
        )
    return text.replace(old, new, 1)


def _scrub_general_bullets(text: str) -> str:
    """Rewrite the handful of §1/§7 bullets that are genuinely general (apply to the
    tables that remain after filtering) but happen to *mention* an excluded table only
    as an illustrative example. Must run before the blanket line-drop, or these bullets
    get deleted wholesale along with the ones that are actually only about excluded
    tables.
    """
    text = _replace_once(
        text,
        "- **Primary keys**: every table (except the `student_360` view and the single "
        "exception `chunk_embeddings`, noted below) has a UUID `id` primary key, "
        "Postgres type `uuid`, application-generated (`uuid4()`), column type `Uuid`.",
        "- **Primary keys**: every table (except the `student_360` view) has a UUID "
        "`id` primary key, Postgres type `uuid`, application-generated (`uuid4()`), "
        "column type `Uuid`.",
        label="the primary-keys convention bullet",
    )
    text = _replace_once(
        text,
        "- **Timestamps**: every table except `audit_events` and `chunk_embeddings` "
        "has `created_at` and `updated_at`, both `TIMESTAMP WITH TIME ZONE`, "
        "server-defaulted to `now()` (`updated_at` also updates `onupdate=now()`). "
        "`audit_events` has `created_at` only (append-only log, never updated); "
        "`chunk_embeddings` has neither (see below).",
        "- **Timestamps**: every table has `created_at` and `updated_at`, both "
        "`TIMESTAMP WITH TIME ZONE`, server-defaulted to `now()` (`updated_at` also "
        "updates `onupdate=now()`).",
        label="the timestamps convention bullet",
    )
    text = _replace_once(
        text,
        "- **Most named `CHECK` constraints in this database are silently "
        "double-prefixed from their intended name** (e.g. the intended "
        "`ck_ingest_jobs_target_kind` was actually stored as "
        "`ck_ingest_jobs_ck_ingest_jobs_target_kind` before migration `b9c0d1e2f3a4` "
        "touched it) — a long-standing bug in how `alembic/env.py` binds "
        "`target_metadata`, affecting every `CheckConstraint(name=...)` declared inside "
        "`op.create_table(...)` across the migration history. This doesn't affect query "
        "results (the `CHECK` still enforces correctly; only its catalog name is "
        "wrong), but it matters if a query inspects "
        "`information_schema.check_constraints`/`pg_constraint` by name, or if you're "
        "writing a migration that needs to `DROP`/`ALTER` one of these by its "
        '"obvious" name — verify the actual name in `pg_constraint` first rather than '
        "assuming it matches the source code's `name=` argument. Not yet fixed "
        "schema-wide; only `chunk_embeddings.doc_kind` and `ingest_jobs`' constraint "
        "(as a side effect of its migration) currently have correct names.",
        "- **Most named `CHECK` constraints in this database are silently "
        "double-prefixed from their intended name** (e.g. `common_mastery_quizzes`' "
        '"exactly one target" constraint, intended as '
        "`ck_common_mastery_quizzes_exactly_one_target`, is actually stored "
        "double-prefixed and hash-truncated) — a long-standing bug in how "
        "`alembic/env.py` binds `target_metadata`, affecting every "
        "`CheckConstraint(name=...)` declared inside `op.create_table(...)` across the "
        "migration history. This doesn't affect query results (the `CHECK` still "
        "enforces correctly; only its catalog name is wrong), but it matters if a "
        "query inspects `information_schema.check_constraints`/`pg_constraint` by "
        "name — verify the actual stored name in `pg_constraint` first rather than "
        "assuming it matches the source code's `name=` argument.",
        label="the double-prefixed CHECK constraint gotcha bullet",
    )
    return text


def _drop_lines_mentioning_excluded(text: str) -> str:
    """Drop every remaining single line that mentions an excluded table by name —
    §1's polymorphic-reference bullet, §3 enum rows and footnotes, §4 FK lines and the
    polymorphic-reference code block, §6 glossary rows, and §7 gotcha bullets. Safe as a
    blanket per-line rule because every one of those is a self-contained line, and
    `_scrub_general_bullets` already rewrote the few lines that mix excluded-table
    mentions with genuinely general, must-survive content.
    """
    excluded = _excluded_pattern()
    return "\n".join(line for line in text.split("\n") if not excluded.search(line))


def _tidy(text: str) -> str:
    """Drop the now-orphaned "Polymorphic references" intro sentence (its code fence
    was emptied by _drop_lines_mentioning_excluded, since every line inside named an
    excluded table), collapse any now-empty code fences, and collapse excess blank
    lines left behind by all of the above.
    """
    text = re.sub(
        r"\*\*Polymorphic references[^\n]*\n\n?",
        "",
        text,
    )
    text = re.sub(r"```\n\n+```\n", "", text)
    # Normalize blank-line runs first, so the separator-collapse pattern below (which
    # expects exactly one blank line between/after `---` markers) actually matches.
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Two adjacent module sections both getting removed (e.g. assistant then rag, back
    # to back) leaves their separators stacked; collapse any run of them to one.
    text = re.sub(r"(?:---\n\n){2,}", "---\n\n", text)
    return text.strip() + "\n"


def _filter_schema_catalog(raw: str) -> str:
    text = raw
    text = _remove_module_section(text, "assistant")
    text = _remove_module_section(text, "rag")
    text = _remove_table_block(text, "audit_events")
    text = _scrub_general_bullets(text)
    text = _drop_lines_mentioning_excluded(text)
    text = _tidy(text)
    _validate_filtered(text)
    return text


def _validate_filtered(text: str) -> None:
    if len(text) < _MIN_LENGTH:
        raise SchemaCatalogError(
            f"filtered schema_context is only {len(text)} chars — expected a full catalog"
        )
    for header in _REQUIRED_HEADERS:
        if header not in text:
            raise SchemaCatalogError(f"filtered schema_context is missing section {header!r}")
    for table in REQUIRED_TABLES:
        if not re.search(rf"\b{re.escape(table)}\b", text):
            raise SchemaCatalogError(
                f"filtered schema_context is missing required table/view {table!r} — "
                "the filter over-stripped"
            )
    leaked = _excluded_pattern().findall(text)
    if leaked:
        raise SchemaCatalogError(
            f"filtered schema_context still contains excluded table(s): {sorted(set(leaked))}"
        )


@lru_cache(maxsize=1)
def _load_filtered_schema_context() -> str:
    try:
        raw = SCHEMA_CATALOG_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise SchemaCatalogError(
            f"schema_catalog.md not readable at {SCHEMA_CATALOG_PATH}: {exc}"
        ) from exc
    return _filter_schema_catalog(raw)


async def load_schema(state: TextToSQLState) -> TextToSQLState:
    try:
        schema_context = _load_filtered_schema_context()
    except SchemaCatalogError as exc:
        return {**state, "error": f"load_schema: {exc}"}
    return {**state, "schema_context": schema_context}

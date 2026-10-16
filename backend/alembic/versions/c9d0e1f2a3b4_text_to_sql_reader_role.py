"""A separate, least-privilege Postgres role for the text-to-SQL pipeline's own reads.

Every other read in this codebase goes through the application's `education` role, which
owns the schema and can do anything to it. That is the wrong role to run LLM-generated SQL
under: `apply_role_scope` (Task 6) and `validate_sql` (Task 5) are the only things standing
between a bad or adversarial question and the data, and both are application code that can
have bugs. `text_to_sql_reader` is a second, independent backstop, enforced by Postgres
itself rather than by anything this project wrote: SELECT-only, and only on the tables
`load_schema.REQUIRED_TABLES` actually lists as in scope for this pipeline.

Two things narrower than a plain per-table grant, matching rules `apply_role_scope`
already enforces at the application layer -- so that if that application-layer check is
ever removed, weakened, or has a bug, the database-level grant still holds the same line:

* `question_answer_keys` gets no grant at all. `apply_role_scope` rejects any reference to
  it outright, for every role; this role simply cannot read it, full stop.
* `users.password_hash` and `refresh_sessions.token_hash` are excluded via column-level
  GRANT (every other column on those two tables is granted normally). `apply_role_scope`
  blocks these two columns by name for every role; this makes that rule true even for a
  query that somehow bypassed application code entirely.

This list is a snapshot of `REQUIRED_TABLES` as of this migration, not a live reference to
it -- migrations are immutable history and must replay identically regardless of what the
application's Python looks like later. If a future task adds a table to `REQUIRED_TABLES`,
it needs its own follow-up migration granting SELECT on it here; nothing enforces that
automatically, since GRANTs don't autogenerate the way table DDL does.

The role's password is read from the `TEXT_TO_SQL_DB_PASSWORD` environment variable at
migration-run time -- the same env var name `Settings.text_to_sql_db_password` binds to
(pydantic-settings' default field->env mapping) -- so setting it once before `alembic
upgrade head` in a real deployment is what the role is actually created with *and* what
the app actually authenticates as; the two can't quietly diverge the way they would if
this were a separate manual `ALTER ROLE` step. Nothing here is a literal secret committed
to git: the fallback below (`text_to_sql_reader`, unused whenever the env var is set) only
ever applies when nothing overrides it, same tier as this project's other unconfigured
dev defaults (`education`/`education`, `jwt_secret`'s "dev-only-change-me").

Revision ID: c9d0e1f2a3b4
Revises: b9c0d1e2f3a4
Create Date: 2026-08-23 00:00:00.000000
"""

import os
from collections.abc import Sequence

from alembic import op

revision: str | Sequence[str] | None = "c9d0e1f2a3b4"
down_revision: str | Sequence[str] | None = "b9c0d1e2f3a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROLE = "text_to_sql_reader"
# Same env var name `Settings.text_to_sql_db_password` reads (pydantic-settings' default
# field->env mapping) -- see module docstring. `''` doubling is standard SQL string-literal
# escaping, needed since this value is spliced into raw DDL text rather than bound as a
# parameter (CREATE ROLE ... PASSWORD does not accept a bind parameter).
_PASSWORD = os.environ.get("TEXT_TO_SQL_DB_PASSWORD", "text_to_sql_reader").replace("'", "''")

# Every REQUIRED_TABLES entry except `question_answer_keys` (no grant at all -- see
# module docstring) and `users`/`refresh_sessions` (column-level grants below instead).
_FULL_TABLE_GRANTS: tuple[str, ...] = (
    "institutions",
    "user_roles",
    "student_profiles",
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

# users: every column except password_hash.
_USERS_COLUMNS = "id, institution_id, email, full_name, status, created_at, updated_at"
# refresh_sessions: every column except token_hash.
_REFRESH_SESSIONS_COLUMNS = "id, user_id, expires_at, revoked_at, created_at, updated_at"


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '{_ROLE}') THEN
                CREATE ROLE {_ROLE} LOGIN PASSWORD '{_PASSWORD}';
            END IF;
        END
        $$;
        """
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {_ROLE}")
    for table in _FULL_TABLE_GRANTS:
        op.execute(f"GRANT SELECT ON {table} TO {_ROLE}")
    op.execute(f"GRANT SELECT ({_USERS_COLUMNS}) ON users TO {_ROLE}")
    op.execute(f"GRANT SELECT ({_REFRESH_SESSIONS_COLUMNS}) ON refresh_sessions TO {_ROLE}")


def downgrade() -> None:
    op.execute(f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {_ROLE}")
    op.execute(f"DROP ROLE IF EXISTS {_ROLE}")

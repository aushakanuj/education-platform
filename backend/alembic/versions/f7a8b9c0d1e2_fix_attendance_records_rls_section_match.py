"""Fix attendance_records RLS teacher policy to match on section, not offering.

**The bug.** The `attendance_records` policy created in migration `e1f2a3b4c5d6`
gates the `teacher` branch on `ta.grade_subject_offering_id =
attendance_records.grade_subject_offering_id`. That column is nullable specifically
because this schema supports two attendance-recording modes -- a per-subject record
(offering populated) and a whole-day record (offering NULL, one row per student per
day, independent of subject). Confirmed live against the seeded data: 100% of
`attendance_records` rows are the whole-day kind (`grade_subject_offering_id IS
NULL` on all 12,000 seeded rows). `NULL` never satisfies `=` against anything,
including another `NULL`, so the teacher branch matched zero attendance rows for
every teacher, unconditionally -- not a data gap, a policy that can structurally
never grant access for the attendance-recording mode actually in use.

This was found, not assumed: `average_attendance_rate` (a live, wired-in text-to-SQL
template) returns `NULL` for every teacher when run as `text_to_sql_reader` with RLS
active, while the identical query run as the superuser `education` role (bypassing
RLS) returns real, non-null attendance percentages for the same students. Confirmed
`attendance_records.section_id` **is** populated on every row -- it is the column
that actually identifies which students a whole-day attendance record covers, the
same column `my_sections`/`list_students_in_section` already use to resolve a
teacher's sections elsewhere in this project.

**The fix.** Replace the teacher branch with one predicate that handles both
recording modes without regressing either:

* Whole-day records (`grade_subject_offering_id IS NULL`, the actual data pattern):
  match purely on section -- does the teacher have an active assignment whose
  offering's `period_grade_id` matches this record's section's `period_grade_id`,
  honoring a section-restricted assignment (`ta.section_id IS NULL OR
  ta.section_id = attendance_records.section_id`) the same way every other
  section-aware policy in `e1f2a3b4c5d6` already does.
* Per-subject records (`grade_subject_offering_id` populated, schema-legal but not
  currently produced by the seed data): keeps the original, stricter behavior on
  top of the section check -- the record's own offering must also match the
  teacher's offering -- so nothing regresses if this recording mode is ever used.

Migrations are immutable history in this project (see `e1f2a3b4c5d6`'s own
docstring) -- this replaces the policy via `DROP POLICY` + `CREATE POLICY` in a new
revision rather than editing the original migration file.

Revision ID: f7a8b9c0d1e2
Revises: e1f2a3b4c5d6
Create Date: 2026-09-05 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str | Sequence[str] | None = "f7a8b9c0d1e2"
down_revision: str | Sequence[str] | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "attendance_records"
_POLICY = f"{_TABLE}_rls_select"

_NEW_USING_EXPR = """
app_student_institution_id(student_id) = app_current_institution_id()
AND (
    app_current_user_role() = 'admin'
    OR (
        app_current_user_role() = 'student'
        AND student_id IN (SELECT id FROM student_profiles WHERE user_id = app_current_user_id())
    )
    OR (
        app_current_user_role() = 'teacher'
        AND EXISTS (
            SELECT 1
            FROM teaching_assignments ta
            JOIN grade_subject_offerings gso ON gso.id = ta.grade_subject_offering_id
            WHERE ta.teacher_user_id = app_current_user_id()
                AND ta.status = 'active'
                AND gso.period_grade_id = (
                    SELECT sec.period_grade_id FROM sections sec
                    WHERE sec.id = attendance_records.section_id
                )
                AND (ta.section_id IS NULL OR ta.section_id = attendance_records.section_id)
                AND (
                    attendance_records.grade_subject_offering_id IS NULL
                    OR attendance_records.grade_subject_offering_id = ta.grade_subject_offering_id
                )
        )
    )
)
"""

_OLD_USING_EXPR = """
app_student_institution_id(student_id) = app_current_institution_id()
AND (
    app_current_user_role() = 'admin'
    OR (
        app_current_user_role() = 'student'
        AND student_id IN (SELECT id FROM student_profiles WHERE user_id = app_current_user_id())
    )
    OR (
        app_current_user_role() = 'teacher'
        AND EXISTS (
            SELECT 1 FROM teaching_assignments ta
            WHERE ta.teacher_user_id = app_current_user_id()
                AND ta.status = 'active'
                AND ta.grade_subject_offering_id = attendance_records.grade_subject_offering_id
                AND (ta.section_id IS NULL OR ta.section_id = attendance_records.section_id)
        )
    )
)
"""


def upgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {_POLICY} ON {_TABLE}")
    op.execute(f"CREATE POLICY {_POLICY} ON {_TABLE} FOR SELECT USING ({_NEW_USING_EXPR})")


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {_POLICY} ON {_TABLE}")
    op.execute(f"CREATE POLICY {_POLICY} ON {_TABLE} FOR SELECT USING ({_OLD_USING_EXPR})")

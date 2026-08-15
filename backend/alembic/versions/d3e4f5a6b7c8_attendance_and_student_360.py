"""Attendance records, and the student_360 master register view.

`student_360` is the single analytical view that dashboards, ask-the-data and the
early-warning engine all read from, so they cannot drift apart. Grain: one row per
student per subject offering per academic period.

Revision ID: d3e4f5a6b7c8
Revises: e5f6a7b8c9d0
Create Date: 2026-08-12 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str | Sequence[str] | None = "d3e4f5a6b7c8"
down_revision: str | Sequence[str] | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


STUDENT_360_SQL = """
CREATE VIEW student_360 AS
WITH quiz_stats AS (
    SELECT
        qa.student_id                                        AS student_id,
        sse.grade_subject_offering_id                        AS grade_subject_offering_id,
        COUNT(*)                                             AS quizzes_taken,
        SUM(CASE WHEN qa.passed IS TRUE THEN 1 ELSE 0 END)   AS quizzes_passed,
        AVG(qa.score_percent)                                AS avg_score_percent,
        MAX(qa.submitted_at)                                 AS last_attempt_at
    FROM quiz_attempts qa
    JOIN student_subject_enrollments sse
      ON sse.id = qa.student_subject_enrollment_id
    WHERE qa.status IN ('submitted', 'scored', 'released')
      AND qa.score_percent IS NOT NULL
    GROUP BY qa.student_id, sse.grade_subject_offering_id
),
attendance_stats AS (
    SELECT
        ar.student_id                                                       AS student_id,
        ar.academic_period_id                                               AS academic_period_id,
        SUM(CASE WHEN ar.status IN ('present','late') THEN 1 ELSE 0 END)    AS days_present,
        SUM(CASE WHEN ar.status <> 'excused' THEN 1 ELSE 0 END)             AS days_counted
    FROM attendance_records ar
    WHERE ar.grade_subject_offering_id IS NULL
    GROUP BY ar.student_id, ar.academic_period_id
),
progress_stats AS (
    SELECT
        sse.student_id                   AS student_id,
        sse.grade_subject_offering_id    AS grade_subject_offering_id,
        SUM(CASE WHEN smp.status = 'completed' THEN 1 ELSE 0 END) AS lessons_completed,
        COUNT(*)                                                  AS lessons_started,
        MAX(smp.updated_at)                                       AS last_progress_at
    FROM student_material_progress smp
    JOIN student_subject_enrollments sse
      ON sse.id = smp.student_subject_enrollment_id
    GROUP BY sse.student_id, sse.grade_subject_offering_id
)
SELECT
    sp.id                          AS student_id,
    sp.institution_id              AS institution_id,
    sp.student_identifier          AS student_identifier,
    sp.full_name                   AS full_name,
    sp.user_id                     AS user_id,
    ap.id                          AS academic_period_id,
    ap.name                        AS academic_period,
    g.id                           AS grade_id,
    g.name                         AS grade,
    sec.id                         AS section_id,
    sec.name                       AS section,
    subj.id                        AS subject_id,
    subj.name                      AS subject,
    gso.id                         AS grade_subject_offering_id,
    sse.id                         AS student_subject_enrollment_id,
    COALESCE(qs.quizzes_taken, 0)  AS quizzes_taken,
    COALESCE(qs.quizzes_passed, 0) AS quizzes_passed,
    ROUND(COALESCE(qs.avg_score_percent, 0)::numeric, 2) AS mastery_percent,
    qs.last_attempt_at             AS last_attempt_at,
    COALESCE(ps.lessons_completed, 0) AS lessons_completed,
    COALESCE(ps.lessons_started, 0)   AS lessons_started,
    ps.last_progress_at            AS last_progress_at,
    COALESCE(ats.days_present, 0)  AS days_present,
    COALESCE(ats.days_counted, 0)  AS days_counted,
    CASE
        WHEN COALESCE(ats.days_counted, 0) = 0 THEN NULL
        ELSE ROUND((ats.days_present * 100.0 / ats.days_counted)::numeric, 2)
    END                            AS attendance_percent
FROM student_subject_enrollments sse
JOIN student_profiles sp            ON sp.id = sse.student_id
JOIN student_grade_enrollments sge  ON sge.id = sse.grade_enrollment_id
JOIN grade_subject_offerings gso    ON gso.id = sse.grade_subject_offering_id
JOIN period_grades pg               ON pg.id = gso.period_grade_id
JOIN grades g                       ON g.id = pg.grade_id
JOIN subjects subj                  ON subj.id = gso.subject_id
JOIN academic_periods ap            ON ap.id = pg.academic_period_id
LEFT JOIN sections sec              ON sec.id = sge.section_id
LEFT JOIN quiz_stats qs
       ON qs.student_id = sse.student_id
      AND qs.grade_subject_offering_id = sse.grade_subject_offering_id
LEFT JOIN progress_stats ps
       ON ps.student_id = sse.student_id
      AND ps.grade_subject_offering_id = sse.grade_subject_offering_id
LEFT JOIN attendance_stats ats
       ON ats.student_id = sse.student_id
      AND ats.academic_period_id = ap.id
WHERE sse.status = 'active' AND sge.status = 'active'
"""


def upgrade() -> None:
    op.create_table(
        "attendance_records",
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("academic_period_id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=True),
        sa.Column("grade_subject_offering_id", sa.Uuid(), nullable=True),
        sa.Column("on_date", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "present",
                "absent",
                "late",
                "excused",
                name="attendance_status",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("recorded_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["academic_period_id"],
            ["academic_periods.id"],
            name=op.f("fk_attendance_records_academic_period_id_academic_periods"),
        ),
        sa.ForeignKeyConstraint(
            ["grade_subject_offering_id"],
            ["grade_subject_offerings.id"],
            name=op.f("fk_attendance_records_grade_subject_offering_id_grade_subject_offerings"),
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"],
            ["users.id"],
            name=op.f("fk_attendance_records_recorded_by_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["section_id"], ["sections.id"], name=op.f("fk_attendance_records_section_id_sections")
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student_profiles.id"],
            name=op.f("fk_attendance_records_student_id_student_profiles"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attendance_records")),
    )
    op.create_index(
        op.f("ix_attendance_records_academic_period_id"),
        "attendance_records",
        ["academic_period_id"],
    )
    op.create_index(
        op.f("ix_attendance_records_grade_subject_offering_id"),
        "attendance_records",
        ["grade_subject_offering_id"],
    )
    op.create_index(op.f("ix_attendance_records_on_date"), "attendance_records", ["on_date"])
    op.create_index(
        op.f("ix_attendance_records_recorded_by_user_id"),
        "attendance_records",
        ["recorded_by_user_id"],
    )
    op.create_index(op.f("ix_attendance_records_section_id"), "attendance_records", ["section_id"])
    op.create_index(op.f("ix_attendance_records_status"), "attendance_records", ["status"])
    op.create_index(op.f("ix_attendance_records_student_id"), "attendance_records", ["student_id"])
    op.create_index(
        "ix_attendance_records_period_date",
        "attendance_records",
        ["academic_period_id", "on_date"],
    )
    op.create_index(
        "uq_attendance_records_day",
        "attendance_records",
        ["student_id", "on_date"],
        unique=True,
        postgresql_where=sa.text("grade_subject_offering_id IS NULL"),
    )
    op.create_index(
        "uq_attendance_records_subject_day",
        "attendance_records",
        ["student_id", "on_date", "grade_subject_offering_id"],
        unique=True,
        postgresql_where=sa.text("grade_subject_offering_id IS NOT NULL"),
    )

    op.execute(STUDENT_360_SQL)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS student_360")
    op.drop_index("uq_attendance_records_subject_day", table_name="attendance_records")
    op.drop_index("uq_attendance_records_day", table_name="attendance_records")
    op.drop_index("ix_attendance_records_period_date", table_name="attendance_records")
    op.drop_index(op.f("ix_attendance_records_student_id"), table_name="attendance_records")
    op.drop_index(op.f("ix_attendance_records_status"), table_name="attendance_records")
    op.drop_index(op.f("ix_attendance_records_section_id"), table_name="attendance_records")
    op.drop_index(
        op.f("ix_attendance_records_recorded_by_user_id"), table_name="attendance_records"
    )
    op.drop_index(op.f("ix_attendance_records_on_date"), table_name="attendance_records")
    op.drop_index(
        op.f("ix_attendance_records_grade_subject_offering_id"), table_name="attendance_records"
    )
    op.drop_index(op.f("ix_attendance_records_academic_period_id"), table_name="attendance_records")
    op.drop_table("attendance_records")

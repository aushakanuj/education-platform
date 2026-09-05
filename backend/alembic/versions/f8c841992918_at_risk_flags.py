"""At-risk early-warning flags.

Implements docs/design/08-at-risk-early-warning.md. One row per (student, subject) for a
mastery-driven concern, or one row per student with `grade_subject_offering_id IS NULL`
for an attendance-only concern (see the spec's Section 7.2 for why attendance has no
single owning subject).

Revision ID: f8c841992918
Revises: d3e4f5a6b7c8
Create Date: 2026-08-29 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str | Sequence[str] | None = "f8c841992918"
down_revision: str | Sequence[str] | None = "d3e4f5a6b7c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "at_risk_flags",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        # NULL means an attendance-only flag -- see the spec's Section 7.2. Never NULL for
        # a mastery-driven flag: that is what lets a teacher's own-offering scope apply.
        sa.Column("grade_subject_offering_id", sa.Uuid(), nullable=True),
        # The flagged student's own class section (from their grade enrollment -- one
        # section per student per grade, constant across every subject they take in it).
        # Not a property of the *concern* -- a flag is about a subject, not a class -- but
        # required for `authorization.predicate.scope_predicate_for`'s exact-(offering,
        # section) teacher grant to work at all. Most real teaching assignments name a
        # specific section rather than a whole offering (confirmed against the live
        # synthetic school), so without this column every section-scoped teacher would see
        # zero flags regardless of what they actually teach. NULL for an attendance-only
        # flag, same as `grade_subject_offering_id`.
        sa.Column("section_id", sa.Uuid(), nullable=True),
        sa.Column("academic_period_id", sa.Uuid(), nullable=False),
        sa.Column("tier", sa.String(length=20), nullable=False),
        # A JSON list of {metric, value, comparison, window}. See engine.py's `Driver`.
        # Never empty -- AR-1 in the spec, enforced in code (engine.py raises rather than
        # producing a driver-less flag) and re-checked by a CHECK constraint here, because
        # a constraint holds even against a caller that bypasses the Python layer.
        sa.Column("drivers", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("dismissed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissal_note", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name="fk_at_risk_flags_institution_id_institutions",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student_profiles.id"],
            name="fk_at_risk_flags_student_id_student_profiles",
        ),
        sa.ForeignKeyConstraint(
            ["grade_subject_offering_id"],
            ["grade_subject_offerings.id"],
            # Shortened by hand -- the fully-spelled-out name exceeds Postgres's 63-byte
            # identifier limit.
            name="fk_at_risk_flags_gso_id_grade_subject_offerings",
        ),
        sa.ForeignKeyConstraint(
            ["section_id"], ["sections.id"], name="fk_at_risk_flags_section_id_sections"
        ),
        sa.ForeignKeyConstraint(
            ["academic_period_id"],
            ["academic_periods.id"],
            name="fk_at_risk_flags_academic_period_id_academic_periods",
        ),
        sa.ForeignKeyConstraint(
            ["dismissed_by_user_id"],
            ["users.id"],
            name="fk_at_risk_flags_dismissed_by_user_id_users",
        ),
        sa.CheckConstraint(
            "tier IN ('monitor', 'attention', 'urgent')", name="ck_at_risk_flags_tier"
        ),
        sa.CheckConstraint(
            "status IN ('active', 'dismissed', 'resolved')", name="ck_at_risk_flags_status"
        ),
        sa.CheckConstraint(
            "jsonb_array_length(drivers::jsonb) > 0", name="ck_at_risk_flags_drivers_not_empty"
        ),
        sa.CheckConstraint(
            "(status = 'active' AND dismissed_by_user_id IS NULL AND dismissed_at IS NULL) OR "
            "(status != 'active')",
            name="ck_at_risk_flags_dismissal_consistency",
        ),
    )
    op.create_index("ix_at_risk_flags_institution_id", "at_risk_flags", ["institution_id"])
    op.create_index("ix_at_risk_flags_student_id", "at_risk_flags", ["student_id"])
    op.create_index(
        "ix_at_risk_flags_grade_subject_offering_id", "at_risk_flags", ["grade_subject_offering_id"]
    )
    op.create_index("ix_at_risk_flags_section_id", "at_risk_flags", ["section_id"])
    op.create_index("ix_at_risk_flags_status", "at_risk_flags", ["status"])
    # One active mastery flag per (student, subject); one active attendance-only flag per
    # student. Recomputing the engine updates the existing row instead of piling up
    # duplicates for the same underlying concern.
    op.create_index(
        "uq_at_risk_flags_active_subject",
        "at_risk_flags",
        ["student_id", "grade_subject_offering_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active' AND grade_subject_offering_id IS NOT NULL"),
    )
    op.create_index(
        "uq_at_risk_flags_active_attendance",
        "at_risk_flags",
        ["student_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active' AND grade_subject_offering_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_at_risk_flags_active_attendance", table_name="at_risk_flags")
    op.drop_index("uq_at_risk_flags_active_subject", table_name="at_risk_flags")
    op.drop_index("ix_at_risk_flags_status", table_name="at_risk_flags")
    op.drop_index("ix_at_risk_flags_section_id", table_name="at_risk_flags")
    op.drop_index("ix_at_risk_flags_grade_subject_offering_id", table_name="at_risk_flags")
    op.drop_index("ix_at_risk_flags_student_id", table_name="at_risk_flags")
    op.drop_index("ix_at_risk_flags_institution_id", table_name="at_risk_flags")
    op.drop_table("at_risk_flags")

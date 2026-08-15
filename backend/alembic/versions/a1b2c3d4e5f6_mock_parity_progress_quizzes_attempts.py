"""mock parity progress quizzes and attempts

Revision ID: a1b2c3d4e5f6
Revises: c78987b61e05
Create Date: 2026-08-10 01:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "c78987b61e05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "student_material_progress",
        sa.Column("student_subject_enrollment_id", sa.Uuid(), nullable=False),
        sa.Column("source_material_version_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("opened", "completed", name="material_progress_status", native_enum=False),
            nullable=False,
        ),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_unit_ordinal", sa.Integer(), nullable=True),
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
        sa.CheckConstraint(
            "(status = 'opened' AND completed_at IS NULL) OR "
            "(status = 'completed' AND completed_at IS NOT NULL)",
            name="ck_student_material_progress_status_timestamps",
        ),
        sa.CheckConstraint(
            "last_unit_ordinal IS NULL OR last_unit_ordinal >= 1",
            name="ck_student_material_progress_last_unit",
        ),
        sa.ForeignKeyConstraint(
            ["source_material_version_id"],
            ["source_material_versions.id"],
            name=op.f(
                "fk_student_material_progress_source_material_version_id_source_material_versions"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["student_subject_enrollment_id"],
            ["student_subject_enrollments.id"],
            name=op.f(
                "fk_student_material_progress_student_subject_enrollment_id_student_subject_enrollments"
            ),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_student_material_progress")),
        sa.UniqueConstraint(
            "student_subject_enrollment_id",
            "source_material_version_id",
            name="uq_student_material_progress_enrollment_version",
        ),
    )
    op.create_index(
        op.f("ix_student_material_progress_source_material_version_id"),
        "student_material_progress",
        ["source_material_version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_student_material_progress_status"),
        "student_material_progress",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_student_material_progress_student_subject_enrollment_id"),
        "student_material_progress",
        ["student_subject_enrollment_id"],
        unique=False,
    )

    with op.batch_alter_table("common_mastery_quizzes") as batch_op:
        batch_op.drop_constraint("uq_common_mastery_quizzes_subtopic", type_="unique")
        batch_op.add_column(
            sa.Column(
                "quiz_scope",
                sa.Enum(
                    "subtopic_mastery",
                    "topic_mastery",
                    name="quiz_scope",
                    native_enum=False,
                ),
                nullable=False,
                server_default="subtopic_mastery",
            )
        )
        batch_op.add_column(sa.Column("topic_id", sa.Uuid(), nullable=True))
        batch_op.alter_column("subtopic_id", existing_type=sa.Uuid(), nullable=True)
        batch_op.create_foreign_key(
            op.f("fk_common_mastery_quizzes_topic_id_topics"),
            "topics",
            ["topic_id"],
            ["id"],
        )
        batch_op.create_index(
            op.f("ix_common_mastery_quizzes_quiz_scope"),
            ["quiz_scope"],
            unique=False,
        )
        batch_op.create_index(
            op.f("ix_common_mastery_quizzes_topic_id"),
            ["topic_id"],
            unique=False,
        )
        batch_op.create_check_constraint(
            "ck_common_mastery_quizzes_exactly_one_target",
            "(quiz_scope = 'subtopic_mastery' AND subtopic_id IS NOT NULL AND topic_id IS NULL) OR "
            "(quiz_scope = 'topic_mastery' AND topic_id IS NOT NULL AND subtopic_id IS NULL)",
        )

    op.create_index(
        "uq_common_mastery_quizzes_subtopic",
        "common_mastery_quizzes",
        ["subtopic_id"],
        unique=True,
        postgresql_where=sa.text("subtopic_id IS NOT NULL"),
    )
    op.create_index(
        "uq_common_mastery_quizzes_topic",
        "common_mastery_quizzes",
        ["topic_id"],
        unique=True,
        postgresql_where=sa.text("topic_id IS NOT NULL"),
    )

    with op.batch_alter_table("quiz_versions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "pass_threshold_percent",
                sa.Numeric(5, 2),
                nullable=False,
                server_default="70.00",
            )
        )
        batch_op.create_check_constraint(
            "ck_quiz_versions_version_number",
            "version_number >= 1",
        )
        batch_op.create_check_constraint(
            "ck_quiz_versions_duration_seconds",
            "duration_seconds IS NULL OR duration_seconds > 0",
        )
        batch_op.create_check_constraint(
            "ck_quiz_versions_max_attempts",
            "max_attempts IS NULL OR max_attempts > 0",
        )

    with op.batch_alter_table("quiz_releases") as batch_op:
        batch_op.alter_column(
            "released_by_user_id",
            existing_type=sa.Uuid(),
            nullable=True,
        )
        batch_op.create_check_constraint(
            "ck_quiz_releases_window_order",
            "window_starts_at IS NULL OR window_ends_at IS NULL OR "
            "window_starts_at <= window_ends_at",
        )

    op.create_index(
        "uq_quiz_releases_one_open_per_version",
        "quiz_releases",
        ["quiz_version_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )

    with op.batch_alter_table("quiz_attempts") as batch_op:
        batch_op.add_column(sa.Column("student_subject_enrollment_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("quiz_release_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("pass_threshold_percent", sa.Numeric(5, 2), nullable=True))
        batch_op.create_foreign_key(
            op.f("fk_quiz_attempts_student_subject_enrollment_id_student_subject_enrollments"),
            "student_subject_enrollments",
            ["student_subject_enrollment_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            op.f("fk_quiz_attempts_quiz_release_id_quiz_releases"),
            "quiz_releases",
            ["quiz_release_id"],
            ["id"],
        )
        batch_op.create_index(
            op.f("ix_quiz_attempts_student_subject_enrollment_id"),
            ["student_subject_enrollment_id"],
            unique=False,
        )
        batch_op.create_index(
            op.f("ix_quiz_attempts_quiz_release_id"),
            ["quiz_release_id"],
            unique=False,
        )
        batch_op.create_check_constraint(
            "ck_quiz_attempts_attempt_number",
            "attempt_number >= 1",
        )
        batch_op.create_check_constraint(
            "ck_quiz_attempts_score_percent",
            "score_percent IS NULL OR (score_percent >= 0 AND score_percent <= 100)",
        )
        batch_op.create_check_constraint(
            "ck_quiz_attempts_pass_threshold",
            "pass_threshold_percent IS NULL OR "
            "(pass_threshold_percent >= 0 AND pass_threshold_percent <= 100)",
        )

    op.create_index(
        "uq_quiz_attempts_one_in_progress",
        "quiz_attempts",
        ["student_subject_enrollment_id", "quiz_version_id"],
        unique=True,
        postgresql_where=sa.text("status = 'in_progress'"),
    )

    with op.batch_alter_table("question_versions") as batch_op:
        batch_op.create_check_constraint(
            "ck_question_versions_version_number",
            "version_number >= 1",
        )
        batch_op.create_check_constraint(
            "ck_question_versions_marks",
            "marks >= 0",
        )

    with op.batch_alter_table("quiz_items") as batch_op:
        batch_op.create_check_constraint(
            "ck_quiz_items_sequence",
            "sequence >= 1",
        )

    with op.batch_alter_table("source_material_versions") as batch_op:
        batch_op.create_check_constraint(
            "ck_source_material_versions_version_number",
            "version_number >= 1",
        )


def downgrade() -> None:
    op.drop_index("uq_quiz_attempts_one_in_progress", table_name="quiz_attempts")
    with op.batch_alter_table("quiz_attempts") as batch_op:
        batch_op.drop_constraint(
            op.f("fk_quiz_attempts_quiz_release_id_quiz_releases"),
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            op.f("fk_quiz_attempts_student_subject_enrollment_id_student_subject_enrollments"),
            type_="foreignkey",
        )
        batch_op.drop_column("pass_threshold_percent")
        batch_op.drop_column("deadline_at")
        batch_op.drop_column("quiz_release_id")
        batch_op.drop_column("student_subject_enrollment_id")

    op.drop_index("uq_quiz_releases_one_open_per_version", table_name="quiz_releases")
    with op.batch_alter_table("quiz_releases") as batch_op:
        batch_op.alter_column(
            "released_by_user_id",
            existing_type=sa.Uuid(),
            nullable=False,
        )

    with op.batch_alter_table("quiz_versions") as batch_op:
        batch_op.drop_column("pass_threshold_percent")

    op.drop_index("uq_common_mastery_quizzes_topic", table_name="common_mastery_quizzes")
    op.drop_index("uq_common_mastery_quizzes_subtopic", table_name="common_mastery_quizzes")
    with op.batch_alter_table("common_mastery_quizzes") as batch_op:
        batch_op.drop_constraint(
            op.f("fk_common_mastery_quizzes_topic_id_topics"),
            type_="foreignkey",
        )
        batch_op.drop_column("topic_id")
        batch_op.drop_column("quiz_scope")
        batch_op.alter_column("subtopic_id", existing_type=sa.Uuid(), nullable=False)
        batch_op.create_unique_constraint(
            "uq_common_mastery_quizzes_subtopic",
            ["subtopic_id"],
        )

    op.drop_table("student_material_progress")

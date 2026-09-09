"""Shared ``student_360`` column lists for insights and at-risk."""

from __future__ import annotations

from education_platform.modules.assessments.models import QuizAttemptStatus
from education_platform.modules.authorization.predicate import ScopeColumns
from education_platform.modules.insights.models import student_360

STUDENT_360_SCOPE_COLUMNS = ScopeColumns(
    institution_id=student_360.c.institution_id,
    student_id=student_360.c.student_id,
    grade_subject_offering_id=student_360.c.grade_subject_offering_id,
    section_id=student_360.c.section_id,
)

FINISHED_ATTEMPT_STATUSES = (
    QuizAttemptStatus.SUBMITTED,
    QuizAttemptStatus.SCORED,
    QuizAttemptStatus.RELEASED,
)

STUDENT_360_SIGNAL_COLUMNS = (
    student_360.c.student_id,
    student_360.c.academic_period_id,
    student_360.c.grade_subject_offering_id,
    student_360.c.mastery_percent,
    student_360.c.quizzes_taken,
    student_360.c.attendance_percent,
    student_360.c.student_subject_enrollment_id,
)

STUDENT_360_IDENTITY_COLUMNS = (
    student_360.c.student_id,
    student_360.c.academic_period_id,
    student_360.c.section_id,
)

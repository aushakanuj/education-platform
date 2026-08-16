"""Scoped reads over the student_360 master register."""

from education_platform.modules.insights.service import Student360Row, query_student_360

__all__ = ["Student360Row", "query_student_360"]

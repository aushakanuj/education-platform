"""POC academic tree used by curriculum seed."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from education_platform.modules.academics.constants import (
    POC_GRADE_NAME,
    POC_INSTITUTION_NAME,
    POC_PERIOD_NAME,
    POC_SUBJECT_CODE,
    POC_TOPIC_SLUG,
)
from education_platform.modules.academics.models import (
    AcademicPeriod,
    AcademicPeriodStatus,
    Grade,
    GradeSubjectOffering,
    PeriodGrade,
    Subject,
    Topic,
)
from education_platform.modules.auth.models import Institution, InstitutionStatus


def ensure_curriculum_root(session: Session) -> Topic:
    """Return the parent Topic that holds approved-material subtopics."""
    institution = session.scalar(
        select(Institution).where(Institution.name == POC_INSTITUTION_NAME)
    )
    if institution is None:
        institution = Institution(
            name=POC_INSTITUTION_NAME,
            timezone="UTC",
            status=InstitutionStatus.ACTIVE,
        )
        session.add(institution)
        session.flush()

    period = session.scalar(
        select(AcademicPeriod).where(
            AcademicPeriod.institution_id == institution.id,
            AcademicPeriod.name == POC_PERIOD_NAME,
        )
    )
    if period is None:
        period = AcademicPeriod(
            institution_id=institution.id,
            name=POC_PERIOD_NAME,
            start_date=date(2026, 6, 1),
            end_date=date(2027, 3, 31),
            status=AcademicPeriodStatus.ACTIVE,
        )
        session.add(period)
        session.flush()
    elif period.status != AcademicPeriodStatus.ACTIVE:
        period.status = AcademicPeriodStatus.ACTIVE

    grade = session.scalar(
        select(Grade).where(
            Grade.institution_id == institution.id,
            Grade.name == POC_GRADE_NAME,
        )
    )
    if grade is None:
        grade = Grade(institution_id=institution.id, name=POC_GRADE_NAME, sort_order=8)
        session.add(grade)
        session.flush()

    subject = session.scalar(
        select(Subject).where(
            Subject.institution_id == institution.id,
            Subject.code == POC_SUBJECT_CODE,
        )
    )
    if subject is None:
        subject = Subject(
            institution_id=institution.id,
            name="Mathematics",
            code=POC_SUBJECT_CODE,
        )
        session.add(subject)
        session.flush()

    period_grade = session.scalar(
        select(PeriodGrade).where(
            PeriodGrade.academic_period_id == period.id,
            PeriodGrade.grade_id == grade.id,
        )
    )
    if period_grade is None:
        period_grade = PeriodGrade(academic_period_id=period.id, grade_id=grade.id)
        session.add(period_grade)
        session.flush()

    offering = session.scalar(
        select(GradeSubjectOffering).where(
            GradeSubjectOffering.period_grade_id == period_grade.id,
            GradeSubjectOffering.subject_id == subject.id,
        )
    )
    if offering is None:
        offering = GradeSubjectOffering(period_grade_id=period_grade.id, subject_id=subject.id)
        session.add(offering)
        session.flush()

    topic = session.scalar(
        select(Topic).where(
            Topic.grade_subject_offering_id == offering.id,
            Topic.slug == POC_TOPIC_SLUG,
        )
    )
    if topic is None:
        topic = Topic(
            grade_subject_offering_id=offering.id,
            name="Approved Materials",
            slug=POC_TOPIC_SLUG,
            sequence=1,
        )
        session.add(topic)
        session.flush()
    return topic

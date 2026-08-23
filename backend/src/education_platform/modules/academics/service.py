"""Curriculum row loading and student enrollment reads.

Permission lives on `Scope`. This module loads rows and looks up enrollment; it does not
decide who may read a lesson or start a quiz.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.modules.academics.models import (
    AcademicPeriod,
    AcademicPeriodStatus,
    EnrollmentStatus,
    Grade,
    GradeSubjectOffering,
    PeriodGrade,
    StudentGradeEnrollment,
    StudentSubjectEnrollment,
    Subject,
    Subtopic,
    Topic,
)
from education_platform.modules.academics.schemas import (
    EnrollmentSummary,
    GradeEnrollmentOut,
    SubjectEnrollmentOut,
)
from education_platform.modules.auth.models import Institution, StudentProfile
from education_platform.modules.authorization.scope import Scope


@dataclass(frozen=True, slots=True)
class CurriculumNode:
    """A subtopic or topic plus the offering/period/institution it sits on."""

    institution: Institution
    period: AcademicPeriod
    offering: GradeSubjectOffering
    topic: Topic
    subtopic: Subtopic | None


async def list_my_enrollments(session: AsyncSession, scope: Scope) -> EnrollmentSummary:
    if scope.self_student_id is None:
        return EnrollmentSummary(
            eligible=False,
            blocked_reason=None,
            grade_enrollments=[],
            subject_enrollments=[],
        )

    grade_rows = (
        await session.execute(
            select(
                StudentGradeEnrollment,
                AcademicPeriod,
                Grade,
                PeriodGrade,
            )
            .join(AcademicPeriod, AcademicPeriod.id == StudentGradeEnrollment.academic_period_id)
            .join(PeriodGrade, PeriodGrade.id == StudentGradeEnrollment.period_grade_id)
            .join(Grade, Grade.id == PeriodGrade.grade_id)
            .where(
                StudentGradeEnrollment.student_id == scope.self_student_id,
                StudentGradeEnrollment.status == EnrollmentStatus.ACTIVE,
                AcademicPeriod.status == AcademicPeriodStatus.ACTIVE,
            )
        )
    ).all()

    subject_rows = (
        await session.execute(
            select(
                StudentSubjectEnrollment,
                GradeSubjectOffering,
                Subject,
                AcademicPeriod,
                Grade,
            )
            .join(
                GradeSubjectOffering,
                GradeSubjectOffering.id == StudentSubjectEnrollment.grade_subject_offering_id,
            )
            .join(Subject, Subject.id == GradeSubjectOffering.subject_id)
            .join(PeriodGrade, PeriodGrade.id == GradeSubjectOffering.period_grade_id)
            .join(Grade, Grade.id == PeriodGrade.grade_id)
            .join(AcademicPeriod, AcademicPeriod.id == PeriodGrade.academic_period_id)
            .where(
                StudentSubjectEnrollment.student_id == scope.self_student_id,
                StudentSubjectEnrollment.status == EnrollmentStatus.ACTIVE,
                AcademicPeriod.status == AcademicPeriodStatus.ACTIVE,
            )
        )
    ).all()

    eligible = bool(grade_rows and subject_rows)
    blocked_reason = None if eligible else "Active Grade 8 Mathematics enrollment required"
    return EnrollmentSummary(
        eligible=eligible,
        blocked_reason=blocked_reason,
        grade_enrollments=[
            GradeEnrollmentOut(
                id=enrollment.id,
                academic_period_id=period.id,
                academic_period_name=period.name,
                academic_period_status=period.status.value,
                grade_id=grade.id,
                grade_name=grade.name,
                status=enrollment.status.value,
            )
            for enrollment, period, grade, _period_grade in grade_rows
        ],
        subject_enrollments=[
            SubjectEnrollmentOut(
                id=enrollment.id,
                grade_subject_offering_id=offering.id,
                academic_period_id=period.id,
                academic_period_name=period.name,
                grade_name=grade.name,
                subject_id=subject.id,
                subject_code=subject.code,
                subject_name=subject.name,
                status=enrollment.status.value,
            )
            for enrollment, offering, subject, period, grade in subject_rows
        ],
    )


async def load_subtopic_node(session: AsyncSession, subtopic_id: UUID) -> CurriculumNode | None:
    """Load a subtopic's curriculum chain. Missing rows return None; no 403s."""
    row = (
        await session.execute(
            select(Subtopic, Topic, GradeSubjectOffering, AcademicPeriod, Institution)
            .select_from(Subtopic)
            .join(Topic, Topic.id == Subtopic.topic_id)
            .join(
                GradeSubjectOffering,
                GradeSubjectOffering.id == Topic.grade_subject_offering_id,
            )
            .join(PeriodGrade, PeriodGrade.id == GradeSubjectOffering.period_grade_id)
            .join(AcademicPeriod, AcademicPeriod.id == PeriodGrade.academic_period_id)
            .join(Institution, Institution.id == AcademicPeriod.institution_id)
            .where(Subtopic.id == subtopic_id)
        )
    ).one_or_none()
    if row is None:
        return None
    subtopic, topic, offering, period, institution = row
    return CurriculumNode(
        institution=institution,
        period=period,
        offering=offering,
        topic=topic,
        subtopic=subtopic,
    )


async def load_topic_node(session: AsyncSession, topic_id: UUID) -> CurriculumNode | None:
    """Load a topic's curriculum chain. Missing rows return None; no 403s."""
    row = (
        await session.execute(
            select(Topic, GradeSubjectOffering, AcademicPeriod, Institution)
            .select_from(Topic)
            .join(
                GradeSubjectOffering,
                GradeSubjectOffering.id == Topic.grade_subject_offering_id,
            )
            .join(PeriodGrade, PeriodGrade.id == GradeSubjectOffering.period_grade_id)
            .join(AcademicPeriod, AcademicPeriod.id == PeriodGrade.academic_period_id)
            .join(Institution, Institution.id == AcademicPeriod.institution_id)
            .where(Topic.id == topic_id)
        )
    ).one_or_none()
    if row is None:
        return None
    topic, offering, period, institution = row
    return CurriculumNode(
        institution=institution,
        period=period,
        offering=offering,
        topic=topic,
        subtopic=None,
    )


async def subject_enrollment_for(
    session: AsyncSession, student_id: UUID, offering_id: UUID
) -> StudentSubjectEnrollment | None:
    """Active subject enrollment for this student on this offering, if any.

    A lookup, not a permission check. Progress and attempts store this row's id.
    """
    return cast(
        StudentSubjectEnrollment | None,
        await session.scalar(
            select(StudentSubjectEnrollment).where(
                StudentSubjectEnrollment.student_id == student_id,
                StudentSubjectEnrollment.grade_subject_offering_id == offering_id,
                StudentSubjectEnrollment.status == EnrollmentStatus.ACTIVE,
            )
        ),
    )


async def enroll_student_in_poc_math(
    session: AsyncSession,
    *,
    student_profile_id: UUID,
) -> None:
    """Test/POC helper: enroll a student in the seeded Grade 8 Mathematics offering."""
    from education_platform.modules.materials.seed import (
        POC_GRADE_NAME,
        POC_INSTITUTION_NAME,
        POC_PERIOD_NAME,
        POC_SUBJECT_CODE,
    )

    institution = await session.scalar(
        select(Institution).where(Institution.name == POC_INSTITUTION_NAME)
    )
    if institution is None:
        raise HTTPException(status_code=404, detail="Seed curriculum first")
    student = await session.get(StudentProfile, student_profile_id)
    if student is None or student.institution_id != institution.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student must belong to the POC institution",
        )
    period = await session.scalar(
        select(AcademicPeriod).where(
            AcademicPeriod.institution_id == institution.id,
            AcademicPeriod.name == POC_PERIOD_NAME,
        )
    )
    grade = await session.scalar(
        select(Grade).where(Grade.institution_id == institution.id, Grade.name == POC_GRADE_NAME)
    )
    subject = await session.scalar(
        select(Subject).where(
            Subject.institution_id == institution.id, Subject.code == POC_SUBJECT_CODE
        )
    )
    if period is None or grade is None or subject is None:
        raise HTTPException(status_code=404, detail="Seed curriculum first")
    period_grade = await session.scalar(
        select(PeriodGrade).where(
            PeriodGrade.academic_period_id == period.id, PeriodGrade.grade_id == grade.id
        )
    )
    if period_grade is None:
        raise HTTPException(status_code=404, detail="Seed curriculum first")
    offering = await session.scalar(
        select(GradeSubjectOffering).where(
            GradeSubjectOffering.period_grade_id == period_grade.id,
            GradeSubjectOffering.subject_id == subject.id,
        )
    )
    if offering is None:
        raise HTTPException(status_code=404, detail="Seed curriculum first")

    existing_grade = await session.scalar(
        select(StudentGradeEnrollment).where(
            StudentGradeEnrollment.student_id == student_profile_id,
            StudentGradeEnrollment.academic_period_id == period.id,
            StudentGradeEnrollment.status == EnrollmentStatus.ACTIVE,
        )
    )
    if existing_grade is None:
        existing_grade = StudentGradeEnrollment(
            student_id=student_profile_id,
            academic_period_id=period.id,
            period_grade_id=period_grade.id,
            status=EnrollmentStatus.ACTIVE,
        )
        session.add(existing_grade)
        await session.flush()

    existing_subject = await session.scalar(
        select(StudentSubjectEnrollment).where(
            StudentSubjectEnrollment.student_id == student_profile_id,
            StudentSubjectEnrollment.grade_subject_offering_id == offering.id,
            StudentSubjectEnrollment.status == EnrollmentStatus.ACTIVE,
        )
    )
    if existing_subject is None:
        session.add(
            StudentSubjectEnrollment(
                student_id=student_profile_id,
                grade_enrollment_id=existing_grade.id,
                grade_subject_offering_id=offering.id,
                status=EnrollmentStatus.ACTIVE,
            )
        )
    await session.commit()

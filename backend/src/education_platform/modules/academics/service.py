"""Enrollment access checks and student enrollment reads."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.api.deps import Principal
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
from education_platform.modules.auth.models import Institution, InstitutionStatus


async def list_my_enrollments(session: AsyncSession, principal: Principal) -> EnrollmentSummary:
    if principal.student_profile_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student profile required",
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
                StudentGradeEnrollment.student_id == principal.student_profile_id,
                StudentGradeEnrollment.status == EnrollmentStatus.ACTIVE,
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
                StudentSubjectEnrollment.student_id == principal.student_profile_id,
                StudentSubjectEnrollment.status == EnrollmentStatus.ACTIVE,
            )
        )
    ).all()

    return EnrollmentSummary(
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


async def assert_can_access_subtopic(
    session: AsyncSession,
    principal: Principal,
    subtopic_id: UUID,
) -> None:
    """Enforce institution + active period + dual enrollment for students."""
    if principal.is_administrator:
        return

    subtopic = await session.get(Subtopic, subtopic_id)
    if subtopic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    row = (
        await session.execute(
            select(Topic, GradeSubjectOffering, PeriodGrade, AcademicPeriod, Institution)
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    _topic, offering, period_grade, period, institution = row
    if institution.id != principal.institution_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    if institution.status != InstitutionStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Institution inactive")
    if period.status != AcademicPeriodStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Academic period inactive"
        )

    if not principal.is_student or principal.student_profile_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Student enrollment required"
        )

    grade_enrollment = await session.scalar(
        select(StudentGradeEnrollment).where(
            StudentGradeEnrollment.student_id == principal.student_profile_id,
            StudentGradeEnrollment.academic_period_id == period.id,
            StudentGradeEnrollment.period_grade_id == period_grade.id,
            StudentGradeEnrollment.status == EnrollmentStatus.ACTIVE,
        )
    )
    if grade_enrollment is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active grade enrollment required",
        )

    subject_enrollment = await session.scalar(
        select(StudentSubjectEnrollment).where(
            StudentSubjectEnrollment.student_id == principal.student_profile_id,
            StudentSubjectEnrollment.grade_subject_offering_id == offering.id,
            StudentSubjectEnrollment.status == EnrollmentStatus.ACTIVE,
        )
    )
    if subject_enrollment is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active subject enrollment required",
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

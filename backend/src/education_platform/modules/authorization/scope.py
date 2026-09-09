"""Resolve what a principal may read — see `docs/design/02` section 5.

Teacher reach is a set of (offering, section) pairs, not a grade or subject alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.modules.academics.models import (
    AcademicPeriod,
    AcademicPeriodStatus,
    EnrollmentStatus,
    GradeSubjectOffering,
    PeriodGrade,
    StudentGradeEnrollment,
    StudentSubjectEnrollment,
    TeachingAssignment,
    TeachingAssignmentStatus,
)
from education_platform.modules.auth.models import RoleName

OfferingSection = tuple[UUID, UUID | None]


class ScopePrincipal(Protocol):
    @property
    def institution_id(self) -> UUID: ...

    @property
    def roles(self) -> frozenset[str]: ...

    @property
    def user_id(self) -> UUID: ...

    @property
    def student_profile_id(self) -> UUID | None: ...


@dataclass(frozen=True, slots=True)
class Scope:
    """What this principal may read."""

    institution_id: UUID
    roles: frozenset[str]
    unrestricted: bool
    taught_offering_sections: frozenset[OfferingSection]
    enrolled_offering_sections: frozenset[OfferingSection]
    student_ids: frozenset[UUID]
    self_student_id: UUID | None

    @property
    def offering_sections(self) -> frozenset[OfferingSection]:
        """Taught or enrolled pairs — descriptive only, not for filtering reads."""
        return self.taught_offering_sections | self.enrolled_offering_sections

    @property
    def offering_ids(self) -> frozenset[UUID]:
        return frozenset(offering for offering, _ in self.offering_sections)

    @property
    def taught_offering_ids(self) -> frozenset[UUID]:
        """Offerings taught, ignoring section — use for subject-level authoring, not reads."""
        return frozenset(offering for offering, _ in self.taught_offering_sections)

    @property
    def section_ids(self) -> frozenset[UUID]:
        return frozenset(section for _, section in self.offering_sections if section is not None)

    @property
    def is_empty(self) -> bool:
        if self.unrestricted:
            return False
        return self.self_student_id is None and not self.taught_offering_sections

    def allows_student(self, student_id: UUID | None) -> bool:
        """Coarse check — whether the student is addressable, not which rows to return."""
        if student_id is None:
            return False
        if self.unrestricted:
            return True
        return student_id in self.student_ids

    def teaches_offering(self, offering_id: UUID, section_id: UUID | None = None) -> bool:
        return self.unrestricted or _matches(self.taught_offering_sections, offering_id, section_id)

    def allows_offering(self, offering_id: UUID, section_id: UUID | None = None) -> bool:
        return self.unrestricted or _matches(self.offering_sections, offering_id, section_id)

    def covers_offering(self, offering_id: UUID, *, institution_id: UUID) -> bool:
        """Offering in scope without a section (lessons, quizzes)."""
        if institution_id != self.institution_id:
            return False
        return self.unrestricted or offering_id in self.offering_ids


def _matches(pairs: frozenset[OfferingSection], offering: UUID, section: UUID | None) -> bool:
    for allowed_offering, allowed_section in pairs:
        if allowed_offering != offering:
            continue
        if allowed_section is None or allowed_section == section:
            return True
    return False


async def _active_period_ids(session: AsyncSession, institution_id: UUID) -> list[UUID]:
    return list(
        await session.scalars(
            select(AcademicPeriod.id).where(
                AcademicPeriod.institution_id == institution_id,
                AcademicPeriod.status == AcademicPeriodStatus.ACTIVE,
            )
        )
    )


async def _teacher_offering_sections(
    session: AsyncSession, teacher_user_id: UUID, period_ids: list[UUID]
) -> set[OfferingSection]:
    if not period_ids:
        return set()
    rows = await session.execute(
        select(
            TeachingAssignment.grade_subject_offering_id,
            TeachingAssignment.section_id,
        ).where(
            TeachingAssignment.teacher_user_id == teacher_user_id,
            TeachingAssignment.academic_period_id.in_(period_ids),
            TeachingAssignment.status == TeachingAssignmentStatus.ACTIVE,
        )
    )
    return {(offering_id, section_id) for offering_id, section_id in rows.all()}


async def _students_for_offering_sections(
    session: AsyncSession, pairs: set[OfferingSection]
) -> set[UUID]:
    if not pairs:
        return set()

    any_section_offerings = {offering for offering, section in pairs if section is None}
    scoped_pairs = {(offering, section) for offering, section in pairs if section is not None}

    student_ids: set[UUID] = set()

    if any_section_offerings:
        student_ids.update(
            await session.scalars(
                select(StudentSubjectEnrollment.student_id).where(
                    StudentSubjectEnrollment.grade_subject_offering_id.in_(any_section_offerings),
                    StudentSubjectEnrollment.status == EnrollmentStatus.ACTIVE,
                )
            )
        )

    for offering_id, section_id in scoped_pairs:
        student_ids.update(
            await session.scalars(
                select(StudentSubjectEnrollment.student_id)
                .join(
                    StudentGradeEnrollment,
                    StudentGradeEnrollment.id == StudentSubjectEnrollment.grade_enrollment_id,
                )
                .where(
                    StudentSubjectEnrollment.grade_subject_offering_id == offering_id,
                    StudentSubjectEnrollment.status == EnrollmentStatus.ACTIVE,
                    StudentGradeEnrollment.section_id == section_id,
                    StudentGradeEnrollment.status == EnrollmentStatus.ACTIVE,
                )
            )
        )

    return student_ids


async def _student_offering_sections(
    session: AsyncSession, student_profile_id: UUID, period_ids: list[UUID]
) -> set[OfferingSection]:
    if not period_ids:
        return set()
    rows = await session.execute(
        select(
            StudentSubjectEnrollment.grade_subject_offering_id,
            StudentGradeEnrollment.section_id,
        )
        .join(
            StudentGradeEnrollment,
            StudentGradeEnrollment.id == StudentSubjectEnrollment.grade_enrollment_id,
        )
        .join(
            GradeSubjectOffering,
            GradeSubjectOffering.id == StudentSubjectEnrollment.grade_subject_offering_id,
        )
        .join(PeriodGrade, PeriodGrade.id == GradeSubjectOffering.period_grade_id)
        .where(
            StudentSubjectEnrollment.student_id == student_profile_id,
            StudentSubjectEnrollment.status == EnrollmentStatus.ACTIVE,
            StudentGradeEnrollment.status == EnrollmentStatus.ACTIVE,
            PeriodGrade.academic_period_id.in_(period_ids),
        )
    )
    return {(offering_id, section_id) for offering_id, section_id in rows.all()}


async def scope_for(session: AsyncSession, principal: ScopePrincipal) -> Scope:
    institution_id = principal.institution_id
    roles = principal.roles
    user_id = principal.user_id
    profile_id = principal.student_profile_id
    self_student_id = profile_id if RoleName.STUDENT.value in roles else None

    if RoleName.ADMINISTRATOR.value in roles:
        return Scope(
            institution_id=institution_id,
            roles=roles,
            unrestricted=True,
            taught_offering_sections=frozenset(),
            enrolled_offering_sections=frozenset(),
            student_ids=frozenset(),
            self_student_id=self_student_id,
        )

    period_ids = await _active_period_ids(session, institution_id)
    taught: set[OfferingSection] = set()
    enrolled: set[OfferingSection] = set()
    student_ids: set[UUID] = set()

    if RoleName.TEACHER.value in roles:
        taught = await _teacher_offering_sections(session, user_id, period_ids)
        student_ids |= await _students_for_offering_sections(session, taught)

    if self_student_id is not None:
        enrolled = await _student_offering_sections(session, self_student_id, period_ids)
        student_ids.add(self_student_id)

    return Scope(
        institution_id=institution_id,
        roles=roles,
        unrestricted=False,
        taught_offering_sections=frozenset(taught),
        enrolled_offering_sections=frozenset(enrolled),
        student_ids=frozenset(student_ids),
        self_student_id=self_student_id,
    )

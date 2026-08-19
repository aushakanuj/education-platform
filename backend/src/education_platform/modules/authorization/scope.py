"""Resolve what a principal is allowed to see, once, before any data is read.

Implements the decision model in `docs/design/02-identity-tenancy-and-authorization.md`
section 5. Every governed read must filter through a `Scope` produced here rather than
writing its own permission check, so that authorization is testable in one place.

The important shape: a teacher's reach is a set of **(offering, section) pairs**, not a
grade and not a subject. A teacher of Grade 8 Mathematics and Grade 9 Science may read
Grade 9 Science students but not Grade 9 Mathematics students.
"""

from __future__ import annotations

from dataclasses import dataclass
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

# A teaching assignment reaches either one section of an offering, or -- when
# section_id is NULL -- every section of that offering.
OfferingSection = tuple[UUID, UUID | None]


@dataclass(frozen=True, slots=True)
class Scope:
    """The complete answer to "what may this principal read?"."""

    institution_id: UUID
    roles: frozenset[str]
    #: Administrators read the whole institution and are not narrowed further.
    unrestricted: bool
    #: Pairs this principal **teaches**. Each one grants every student in it.
    taught_offering_sections: frozenset[OfferingSection]
    #: Pairs this principal is **enrolled in**. These grant nothing beyond the principal's
    #: own rows, which `self_student_id` already covers -- they are carried only so the
    #: interface can say which subjects a student is taking.
    enrolled_offering_sections: frozenset[OfferingSection]
    #: Student profile ids this principal may reach *at all*. Empty when `unrestricted`.
    #: Coarser than the row-level boundary -- see `allows_student`.
    student_ids: frozenset[UUID]
    #: The principal's own student profile, when they hold the student role.
    self_student_id: UUID | None

    @property
    def offering_sections(self) -> frozenset[OfferingSection]:
        """Every pair this principal touches, taught or enrolled.

        Descriptive only. Never filter a read on this: it mixes "I teach this, so I may see
        everyone in it" with "I study this, so I may see myself in it".
        """
        return self.taught_offering_sections | self.enrolled_offering_sections

    @property
    def offering_ids(self) -> frozenset[UUID]:
        return frozenset(offering for offering, _ in self.offering_sections)

    @property
    def taught_offering_ids(self) -> frozenset[UUID]:
        """Offerings the principal teaches, ignoring which sections.

        For decisions about a *subject* rather than a *class* -- authoring a question for
        a subtopic, say, which belongs to the offering and not to any one section. Do not
        use `teaches_offering(offering)` for this: with no section argument it asks "do you
        teach every section of this?", which is false for an ordinary section-scoped
        assignment and would refuse a teacher access to her own subject.
        """
        return frozenset(offering for offering, _ in self.taught_offering_sections)

    @property
    def section_ids(self) -> frozenset[UUID]:
        return frozenset(section for _, section in self.offering_sections if section is not None)

    @property
    def is_empty(self) -> bool:
        """True when this principal can reach no student data at all.

        Mirrors `insights.service.scope_predicate`: data is reached through one's own
        student record or through what one teaches, and by no other route.
        """
        if self.unrestricted:
            return False
        return self.self_student_id is None and not self.taught_offering_sections

    def allows_student(self, student_id: UUID | None) -> bool:
        """Whether this student is in the principal's world at all.

        Deliberately coarser than a read: a teacher of Grade 8 Mathematics `allows_student`
        their Maths pupils, but must still not see those pupils' Science marks. Use this to
        decide whether a student is addressable, never to decide which of their rows to
        return -- that is `scope_predicate`'s job.
        """
        if student_id is None:
            return False
        if self.unrestricted:
            return True
        return student_id in self.student_ids

    def teaches_offering(self, offering_id: UUID, section_id: UUID | None = None) -> bool:
        """Whether the principal teaches this pair, and so may read every student in it."""
        return self.unrestricted or _matches(self.taught_offering_sections, offering_id, section_id)

    def allows_offering(self, offering_id: UUID, section_id: UUID | None = None) -> bool:
        """Whether this pair is in the principal's world, taught or studied."""
        return self.unrestricted or _matches(self.offering_sections, offering_id, section_id)


def _matches(pairs: frozenset[OfferingSection], offering: UUID, section: UUID | None) -> bool:
    """A NULL-section pair covers every section of that offering."""
    for allowed_offering, allowed_section in pairs:
        if allowed_offering != offering:
            continue
        if allowed_section is None or allowed_section == section:
            return True
    return False


async def _active_period_ids(session: AsyncSession, institution_id: UUID) -> list[UUID]:
    """Step 4 of the decision model: only active periods are in scope."""
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
    """Students enrolled in those offerings, narrowed by section where one is named."""
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


async def scope_for(session: AsyncSession, principal: object) -> Scope:
    """Build the scope for an authenticated principal.

    `principal` is an `api.deps.Principal`; it is typed loosely here to keep this module
    importable from `api.deps` without a circular import.
    """
    institution_id: UUID = principal.institution_id  # type: ignore[attr-defined]
    roles: frozenset[str] = principal.roles  # type: ignore[attr-defined]
    user_id: UUID = principal.user_id  # type: ignore[attr-defined]
    profile_id: UUID | None = principal.student_profile_id  # type: ignore[attr-defined]
    # A profile attached to the account is not itself a grant; the student role is.
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

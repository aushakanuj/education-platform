"""Task 3.6 — generate draft quiz questions from a subtopic's learning outcomes.

Three rules shape everything here.

**Drafts are drafts.** Generated questions are written with
``QuestionVersionStatus.DRAFT`` and are never attached to a quiz. A student cannot reach
them because the student-facing paths read published questions through ``quiz_items``, and
nothing here touches that table. Publishing is a separate, deliberate act by a person.

**A teacher authors only where they teach.** A subtopic belongs to a topic, which belongs
to a grade-subject offering -- the same offering the permission model already reasons
about, so authorisation reuses ``Scope`` rather than inventing a rule. It checks
``scope.taught_offering_ids`` and *not* ``teaches_offering(offering)``: with no section
argument the latter asks "do you teach every section of this?", which is false for an
ordinary section-scoped assignment and would lock a teacher out of her own subject.

**The model's output is untrusted.** Every question is validated before it is stored --
four options, exactly one correct, no duplicates, nothing empty. A malformed question is
dropped with a reason rather than saved and discovered by a child in an exam.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from education_platform.modules.academics.models import (
    GradeSubjectOffering,
    LearningOutcome,
    Subject,
    Subtopic,
    Topic,
)
from education_platform.modules.assessments.models import (
    Question,
    QuestionAnswerKey,
    QuestionDifficulty,
    QuestionOption,
    QuestionOutcomeTag,
    QuestionType,
    QuestionVersion,
    QuestionVersionStatus,
)
from education_platform.modules.assistant.openrouter import OpenRouterError, chat_completion_json
from education_platform.modules.authorization.scope import Scope

#: Multiple choice only. Written answers are never machine-marked on this project, so
#: generating them would create work a teacher cannot use.
OPTION_LABELS = ("A", "B", "C", "D")
MAX_PER_REQUEST = 10


class AuthoringError(Exception):
    """Raised when generation cannot proceed. The message is safe to show a teacher."""


@dataclass(frozen=True, slots=True)
class DraftQuestion:
    prompt: str
    options: dict[str, str]
    correct_label: str
    explanation: str
    difficulty: QuestionDifficulty


@dataclass(slots=True)
class GenerationResult:
    subtopic_id: UUID
    subtopic_name: str
    created: list[UUID] = field(default_factory=list)
    #: Questions the model produced that failed validation, with the reason. Surfaced
    #: rather than hidden: a model that keeps failing one rule is worth knowing about.
    rejected: list[str] = field(default_factory=list)


QuestionWriter = Callable[[str], Awaitable[list[dict[str, object]]]]


def _prompt_for(
    subtopic_name: str,
    subject: str,
    grade: str,
    outcomes: list[str],
    count: int,
    difficulty: QuestionDifficulty,
) -> str:
    outcome_lines = "\n".join(f"  - {statement}" for statement in outcomes) or "  - (none recorded)"
    return (
        f"Write {count} multiple-choice questions for {grade} {subject}, on the subtopic "
        f'"{subtopic_name}".\n\n'
        f"Learning outcomes to assess:\n{outcome_lines}\n\n"
        f"Difficulty: {difficulty.value}.\n\n"
        "Reply with JSON only, in this exact shape:\n"
        '{"questions": [{"prompt": "...", "options": {"A": "...", "B": "...", "C": "...", '
        '"D": "..."}, "correct": "A", "explanation": "..."}]}\n\n'
        "Rules:\n"
        "  - Exactly four options, labelled A, B, C and D.\n"
        "  - Exactly one is correct.\n"
        "  - The three wrong options must be plausible: a common misunderstanding, not an\n"
        "    obviously silly answer. A question everyone gets right teaches nobody anything.\n"
        "  - Do not write 'all of the above' or 'none of the above'.\n"
        "  - The explanation says why the correct answer is correct, in one sentence a\n"
        "    student would understand.\n"
        "  - Ask about the outcomes above, not about trivia surrounding them."
    )


async def _openrouter_writer(prompt: str) -> list[dict[str, object]]:
    payload = await chat_completion_json(
        [
            {
                "role": "system",
                "content": (
                    "You write assessment questions for schoolteachers. You return JSON only."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.4,
    )
    questions = payload.get("questions")
    return list(questions) if isinstance(questions, list) else []


def validate(raw: object) -> DraftQuestion | str:
    """Turn one model-produced question into a `DraftQuestion`, or say why it cannot be.

    Returns the reason as a string rather than raising: one bad question in five should
    cost that question, not the whole request.
    """
    if not isinstance(raw, dict):
        return "not an object"

    prompt = str(raw.get("prompt") or "").strip()
    if len(prompt) < 10:
        return "prompt missing or too short"

    options_raw = raw.get("options")
    if not isinstance(options_raw, dict):
        return f"{prompt[:40]}…: options missing"

    options = {str(k).strip().upper(): str(v).strip() for k, v in options_raw.items()}
    if set(options) != set(OPTION_LABELS):
        return f"{prompt[:40]}…: needs exactly options A-D"
    if any(not text for text in options.values()):
        return f"{prompt[:40]}…: an option is empty"

    lowered = [text.lower() for text in options.values()]
    if len(set(lowered)) != len(lowered):
        return f"{prompt[:40]}…: duplicate options"
    if any(text.startswith(("all of the above", "none of the above")) for text in lowered):
        return f"{prompt[:40]}…: 'all/none of the above' is not allowed"

    correct = str(raw.get("correct") or "").strip().upper()
    if correct not in options:
        return f"{prompt[:40]}…: correct answer is not one of the options"

    difficulty_raw = str(raw.get("difficulty") or "medium").strip().lower()
    try:
        difficulty = QuestionDifficulty(difficulty_raw)
    except ValueError:
        difficulty = QuestionDifficulty.MEDIUM

    return DraftQuestion(
        prompt=prompt,
        options=options,
        correct_label=correct,
        explanation=str(raw.get("explanation") or "").strip(),
        difficulty=difficulty,
    )


async def _authorised_subtopic(
    session: AsyncSession, scope: Scope, subtopic_id: UUID
) -> tuple[Subtopic, str, str, UUID]:
    """The subtopic, its subject and grade, and the offering it sits under.

    Refuses when the caller does not teach the offering. This is a *capability* failure --
    authoring is an action, not a read -- so it raises rather than returning nothing.
    """
    row = (
        await session.execute(
            select(
                Subtopic,
                Subject.name,
                Topic.grade_subject_offering_id,
                Subject.institution_id,
            )
            .join(Topic, Topic.id == Subtopic.topic_id)
            .join(GradeSubjectOffering, GradeSubjectOffering.id == Topic.grade_subject_offering_id)
            .join(Subject, Subject.id == GradeSubjectOffering.subject_id)
            .where(Subtopic.id == subtopic_id)
        )
    ).first()
    if row is None:
        raise AuthoringError("That subtopic does not exist.")

    subtopic, subject_name, offering_id, subject_institution_id = row
    # Same answer as a missing subtopic: confirming another school's curriculum exists would
    # itself be the disclosure. Insights uses the same shape for out-of-scope students.
    if subject_institution_id != scope.institution_id:
        raise AuthoringError("That subtopic does not exist.")
    # Per-offering, not per-section: a subtopic belongs to the subject, so teaching any one
    # section of it is enough to author for it.
    if not (scope.unrestricted or offering_id in scope.taught_offering_ids):
        raise AuthoringError("You do not teach this subject, so you cannot author for it.")

    topic = await session.get(Topic, subtopic.topic_id)
    grade_name = topic.name if topic else ""
    return subtopic, subject_name, grade_name, offering_id


async def generate_questions(
    session: AsyncSession,
    scope: Scope,
    subtopic_id: UUID,
    *,
    count: int = 5,
    difficulty: QuestionDifficulty = QuestionDifficulty.MEDIUM,
    write_questions: QuestionWriter | None = None,
) -> GenerationResult:
    """Generate `count` draft questions for a subtopic the caller teaches."""
    count = max(1, min(count, MAX_PER_REQUEST))
    subtopic, subject_name, topic_name, _ = await _authorised_subtopic(session, scope, subtopic_id)

    outcomes = list(
        await session.scalars(
            select(LearningOutcome)
            .where(LearningOutcome.subtopic_id == subtopic_id)
            .order_by(LearningOutcome.sequence)
        )
    )

    writer = write_questions or _openrouter_writer
    prompt = _prompt_for(
        subtopic.name,
        subject_name,
        topic_name,
        [outcome.statement for outcome in outcomes],
        count,
        difficulty,
    )
    try:
        raw_questions = await writer(prompt)
    except OpenRouterError as exc:
        raise AuthoringError(str(exc)) from exc

    result = GenerationResult(subtopic_id=subtopic_id, subtopic_name=subtopic.name)
    if not raw_questions:
        result.rejected.append("The model returned no questions.")
        return result

    for raw in raw_questions[:count]:
        validated = validate(raw)
        if isinstance(validated, str):
            result.rejected.append(validated)
            continue
        version_id = await _persist(session, subtopic_id, validated, outcomes)
        result.created.append(version_id)

    await session.flush()
    return result


async def _persist(
    session: AsyncSession,
    subtopic_id: UUID,
    draft: DraftQuestion,
    outcomes: list[LearningOutcome],
) -> UUID:
    question = Question(subtopic_id=subtopic_id)
    session.add(question)
    await session.flush()

    version = QuestionVersion(
        question_id=question.id,
        version_number=1,
        prompt=draft.prompt,
        question_type=QuestionType.MULTIPLE_CHOICE,
        difficulty=draft.difficulty,
        marks=Decimal("1.00"),
        explanation=draft.explanation or None,
        lifecycle_status=QuestionVersionStatus.DRAFT,
    )
    session.add(version)
    await session.flush()

    for sequence, label in enumerate(OPTION_LABELS):
        session.add(
            QuestionOption(
                question_version_id=version.id,
                label=label,
                text=draft.options[label],
                sequence=sequence,
            )
        )

    # The key lives in its own table and is never joined from student-facing paths.
    session.add(
        QuestionAnswerKey(
            question_version_id=version.id,
            correct_option_label=draft.correct_label,
        )
    )

    for outcome in outcomes:
        session.add(
            QuestionOutcomeTag(question_version_id=version.id, learning_outcome_id=outcome.id)
        )

    return version.id


async def list_questions(
    session: AsyncSession,
    scope: Scope,
    subtopic_id: UUID,
    status: QuestionVersionStatus = QuestionVersionStatus.DRAFT,
) -> list[tuple[QuestionVersion, list[QuestionOption], str | None]]:
    """Questions for a subtopic in one lifecycle state, with options and correct answer.

    The answer is included because this is the *authoring* path -- a teacher reviewing a
    draft must see which option is marked correct in order to judge it, and one reading
    back the approved bank needs the same to check what they approved.

    Reachable only by someone who teaches the subject, whichever status is asked for:
    published questions are still answer keys, and an answer key is not a student's to read.
    """
    await _authorised_subtopic(session, scope, subtopic_id)

    versions = list(
        await session.scalars(
            select(QuestionVersion)
            .join(Question, Question.id == QuestionVersion.question_id)
            .where(
                Question.subtopic_id == subtopic_id,
                QuestionVersion.lifecycle_status == status,
            )
            .order_by(QuestionVersion.created_at)
        )
    )

    out = []
    for version in versions:
        options = list(
            await session.scalars(
                select(QuestionOption)
                .where(QuestionOption.question_version_id == version.id)
                .order_by(QuestionOption.sequence)
            )
        )
        key = await session.scalar(
            select(QuestionAnswerKey.correct_option_label).where(
                QuestionAnswerKey.question_version_id == version.id
            )
        )
        out.append((version, options, key))
    return out


async def _authorised_version(
    session: AsyncSession, scope: Scope, version_id: UUID
) -> QuestionVersion:
    version = await session.get(QuestionVersion, version_id)
    if version is None:
        raise AuthoringError("That question does not exist.")
    question = await session.get(Question, version.question_id)
    if question is None:
        raise AuthoringError("That question does not exist.")
    await _authorised_subtopic(session, scope, question.subtopic_id)
    return version


async def publish_draft(session: AsyncSession, scope: Scope, version_id: UUID) -> QuestionVersion:
    """Move one draft to published. Deliberately one at a time -- a teacher approves each."""
    version = await _authorised_version(session, scope, version_id)
    if version.lifecycle_status != QuestionVersionStatus.DRAFT:
        raise AuthoringError("Only a draft can be published.")
    version.lifecycle_status = QuestionVersionStatus.PUBLISHED
    await session.flush()
    return version


async def discard_draft(session: AsyncSession, scope: Scope, version_id: UUID) -> None:
    """Archive rather than delete: what was rejected is worth keeping."""
    version = await _authorised_version(session, scope, version_id)
    if version.lifecycle_status != QuestionVersionStatus.DRAFT:
        raise AuthoringError("Only a draft can be discarded.")
    version.lifecycle_status = QuestionVersionStatus.ARCHIVED
    await session.flush()


def _status_count(status: QuestionVersionStatus, label: str) -> Any:
    """Per-subtopic count of question versions in one lifecycle state."""
    return (
        select(Question.subtopic_id, func.count().label(label))
        .join(QuestionVersion, QuestionVersion.question_id == Question.id)
        .where(QuestionVersion.lifecycle_status == status)
        .group_by(Question.subtopic_id)
        .subquery()
    )


async def authorable_subtopics(
    session: AsyncSession, scope: Scope
) -> list[tuple[Subtopic, str, str, int, int]]:
    """Subtopics the caller may author for, with subject, topic, and both bank counts.

    Both counts, because a teacher who has just approved a question needs to see where it
    went. A draft count alone drops to zero on approval and looks like the work vanished.
    """
    if scope.unrestricted:
        offering_filter = None
    else:
        offerings = sorted({offering for offering, _ in scope.taught_offering_sections}, key=str)
        if not offerings:
            return []
        offering_filter = offerings

    draft_count = _status_count(QuestionVersionStatus.DRAFT, "drafts")
    published_count = _status_count(QuestionVersionStatus.PUBLISHED, "published")

    # Institution is always pinned. `unrestricted` means the whole school, not every school:
    # insights.scope_predicate does the same, and skipping this filter let an administrator
    # list and author another tenant's questions, including answer keys.
    statement = (
        select(
            Subtopic,
            Subject.name,
            Topic.name,
            func.coalesce(draft_count.c.drafts, 0),
            func.coalesce(published_count.c.published, 0),
        )
        .join(Topic, Topic.id == Subtopic.topic_id)
        .join(GradeSubjectOffering, GradeSubjectOffering.id == Topic.grade_subject_offering_id)
        .join(Subject, Subject.id == GradeSubjectOffering.subject_id)
        .outerjoin(draft_count, draft_count.c.subtopic_id == Subtopic.id)
        .outerjoin(published_count, published_count.c.subtopic_id == Subtopic.id)
        .where(Subject.institution_id == scope.institution_id)
        .order_by(Subject.name, Topic.sequence, Subtopic.sequence)
    )
    if offering_filter is not None:
        statement = statement.where(Topic.grade_subject_offering_id.in_(offering_filter))

    rows = await session.execute(statement)
    return [
        (subtopic, subject, topic, int(drafts), int(published))
        for subtopic, subject, topic, drafts, published in rows
    ]

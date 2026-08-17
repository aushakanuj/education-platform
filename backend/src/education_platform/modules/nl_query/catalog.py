"""Task 2.1 — the description of the data that is sent to the model.

The model never sees a student record. It sees only this description: the column names,
what each one means, and the shape of the values. Everything it knows about the school it
knows from here, which is why this file is reviewed like code rather than tucked inside a
prompt string.

Two rules govern what belongs here:

* **Describe, never disclose.** Sample values are illustrative and drawn from the
  vocabulary of the schema (grade names, subject names), never from a real row.
* **Say what is wrong as well as what is right.** The model does not need to be told the
  security rules -- the guardrail applies those regardless -- but it produces far better
  SQL when told which columns are not worth filtering on and why.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The only relation a generated query may read. The guardrail enforces this; the catalog
#: exists so the model does not try anything else in the first place.
TABLE_NAME = "student_360"


@dataclass(frozen=True, slots=True)
class Column:
    name: str
    sql_type: str
    meaning: str
    values: str


@dataclass(frozen=True, slots=True)
class Example:
    question: str
    sql: str


COLUMNS: tuple[Column, ...] = (
    Column("student_id", "uuid", "Identifies the student. Use for COUNT(DISTINCT ...).", "opaque"),
    Column("student_identifier", "text", "The school's own roll number.", "'S-0007'"),
    Column("full_name", "text", "The student's full name.", "'Aisha Rahman'"),
    Column("grade", "text", "Year group.", "'Grade 6' … 'Grade 10'"),
    Column(
        "section",
        "text",
        "Class within a grade. Note the grade number is part of the name. May be NULL.",
        "'8A', '8B', '10A'",
    ),
    Column(
        "subject",
        "text",
        "Subject. One row per student per subject.",
        "'Mathematics', 'Science', 'English', 'Arabic', 'Social Studies'",
    ),
    Column("academic_period", "text", "The term this row covers.", "'Term 1 2026'"),
    Column("quizzes_taken", "integer", "Quizzes attempted in this subject.", "0 – 5"),
    Column("quizzes_passed", "integer", "Of those, how many were passed.", "0 – 5"),
    Column(
        "mastery_percent",
        "numeric",
        "Average quiz score for this subject. The main measure of attainment. "
        "0 means no quizzes were attempted, so exclude it when averaging attainment.",
        "0.00 – 100.00",
    ),
    Column("lessons_completed", "integer", "Lessons finished in this subject.", "0 upwards"),
    Column("lessons_started", "integer", "Lessons begun, whether finished or not.", "0 upwards"),
    Column("days_present", "integer", "School days attended in the term.", "0 upwards"),
    Column(
        "days_counted",
        "integer",
        "School days that counted; excused absence is excluded.",
        "0 upwards",
    ),
    Column(
        "attendance_percent",
        "numeric",
        "days_present / days_counted. Identical across a student's subject rows, because "
        "attendance is recorded for the school day rather than per lesson. NULL when no "
        "attendance was recorded. Below 75 is the exam-eligibility threshold.",
        "0.00 – 100.00",
    ),
    Column(
        "last_attempt_at", "timestamptz", "When the most recent quiz was submitted.", "NULL if none"
    ),
    Column("last_progress_at", "timestamptz", "When lesson progress last changed.", "NULL if none"),
)

#: Present but deliberately undocumented above: the model has no reason to filter on them,
#: and every attempt to do so is a sign it is trying to scope the query itself.
INTERNAL_COLUMNS: frozenset[str] = frozenset(
    {
        "institution_id",
        "user_id",
        "academic_period_id",
        "grade_id",
        "section_id",
        "subject_id",
        "grade_subject_offering_id",
        "student_subject_enrollment_id",
    }
)

EXAMPLES: tuple[Example, ...] = (
    Example(
        "how many Grade 8 students are below 40% in maths",
        "SELECT COUNT(DISTINCT student_id) AS students\n"
        "FROM student_360\n"
        "WHERE grade = 'Grade 8' AND subject = 'Mathematics' AND mastery_percent < 40",
    ),
    Example(
        "average attendance by grade",
        "SELECT grade, ROUND(AVG(attendance_percent), 1) AS average_attendance\n"
        "FROM student_360\n"
        "WHERE attendance_percent IS NOT NULL\n"
        "GROUP BY grade\n"
        "ORDER BY grade",
    ),
    Example(
        "which students have attendance below 75 percent",
        "SELECT DISTINCT full_name, grade, section, attendance_percent\n"
        "FROM student_360\n"
        "WHERE attendance_percent < 75\n"
        "ORDER BY attendance_percent",
    ),
    Example(
        "compare the two Grade 8 sections in maths",
        "SELECT section, ROUND(AVG(mastery_percent), 1) AS average_mastery, "
        "COUNT(DISTINCT student_id) AS students\n"
        "FROM student_360\n"
        "WHERE grade = 'Grade 8' AND subject = 'Mathematics' AND quizzes_taken > 0\n"
        "GROUP BY section\n"
        "ORDER BY section",
    ),
    Example(
        "who is struggling in one subject but fine in the others",
        "SELECT full_name, subject, mastery_percent\n"
        "FROM student_360 s\n"
        "WHERE quizzes_taken > 0 AND mastery_percent < 60\n"
        "  AND (SELECT AVG(mastery_percent) FROM student_360 o\n"
        "       WHERE o.student_id = s.student_id AND o.subject <> s.subject\n"
        "       AND o.quizzes_taken > 0) > 70\n"
        "ORDER BY mastery_percent",
    ),
)


def column_names() -> frozenset[str]:
    """Documented columns only -- what a generated query is expected to reference."""
    return frozenset(column.name for column in COLUMNS)


def render_catalog() -> str:
    """The description handed to the model with every question."""
    lines = [
        f"You are writing one PostgreSQL SELECT query against a single view: {TABLE_NAME}.",
        "",
        "GRAIN: one row per student, per subject, per academic period. A student taking five",
        "subjects has five rows. Count students with COUNT(DISTINCT student_id), never COUNT(*).",
        "",
        "COLUMNS",
    ]
    width = max(len(column.name) for column in COLUMNS)
    for column in COLUMNS:
        lines.append(f"  {column.name:<{width}}  {column.sql_type:<12} {column.meaning}")
        lines.append(f"  {'':<{width}}  {'':<12} values: {column.values}")
    lines += [
        "",
        "RULES",
        f"  1. Read only from {TABLE_NAME}. No other table or view exists. Never JOIN to one.",
        "  2. Write exactly one SELECT statement. Never INSERT, UPDATE, DELETE, or anything",
        "     that changes data. Never use a semicolon to add a second statement.",
        "  3. Do NOT filter by institution, school, teacher, or the identity of the person",
        "     asking. The platform narrows the rows to what they may see before the query",
        "     runs, so any such filter is at best redundant and at worst wrong.",
        "  4. mastery_percent is 0 for a student who attempted no quizzes. When the question",
        "     is about attainment, add quizzes_taken > 0 so those rows do not drag averages down.",
        "  5. Prefer readable column aliases -- they become the table headings a teacher reads.",
        "",
        "EXAMPLES",
    ]
    for example in EXAMPLES:
        lines.append(f"  -- {example.question}")
        lines.extend(f"  {line}" for line in example.sql.splitlines())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"

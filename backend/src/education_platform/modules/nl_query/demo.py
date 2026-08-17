"""A runnable demonstration of ask-the-data, for showing the team.

    uv run python -m education_platform.modules.nl_query.demo

Needs a generated school (`modules.synthetic.cli`) and nothing else. The AI is not
called unless OPENROUTER_API_KEY is set, because the part worth watching is what the
platform does *after* the model has written its query -- and that is identical whether the
SQL came from a model or from this file.
"""

from __future__ import annotations

import asyncio
import textwrap

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from education_platform.core.config import get_settings
from education_platform.db.url import to_async_url
from education_platform.modules.auth.models import StudentProfile, User, UserRole
from education_platform.modules.authorization.scope import Scope, scope_for
from education_platform.modules.nl_query import service
from education_platform.modules.nl_query.guardrail import GuardrailViolation, guard

WIDTH = 78
QUESTION = "which students are below 60% in any subject?"
MODEL_SQL = "SELECT full_name, subject, mastery_percent FROM student_360 WHERE mastery_percent < 60"

#: Aisha is the planted struggling student -- she has exactly one row under 60%, so the
#: student case shows "my own record" rather than an ambiguous empty result.
CAST = (
    ("Fatima, the principal", "fatima.almansouri@alnoor.school"),
    ("Meera, teaches Grade 8 Maths + Grade 9 Science", "meera.krishnan@alnoor.school"),
    ("Aisha Rahman, a Grade 8 student", "student97@alnoor.school"),
)

REFUSALS = (
    ("Delete every record", "DELETE FROM student_360"),
    ("Change everyone's marks", "UPDATE student_360 SET mastery_percent = 100"),
    ("Smuggle a second command", "SELECT 1 FROM student_360; DROP TABLE users"),
    ("Read the password table", "SELECT email, password_hash FROM users"),
    ("Dodge the boundary by full name", "SELECT full_name FROM public.student_360"),
    ("Tie up the database", "SELECT pg_sleep(300) FROM student_360"),
)


def rule(title: str = "") -> None:
    print("\n" + "=" * WIDTH)
    if title:
        print(title)
        print("=" * WIDTH)


class _Principal:
    def __init__(self, user_id, institution_id, roles, student_profile_id) -> None:  # type: ignore[no-untyped-def]
        self.user_id = user_id
        self.institution_id = institution_id
        self.roles = roles
        self.student_profile_id = student_profile_id


async def _principal(session: AsyncSession, email: str) -> _Principal:
    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        raise SystemExit(
            f"No account {email}. Build the demo school first:\n"
            "  uv run python -m education_platform.modules.synthetic.cli"
        )
    roles = await session.scalars(select(UserRole.role).where(UserRole.user_id == user.id))
    profile = await session.scalar(
        select(StudentProfile.id).where(StudentProfile.user_id == user.id)
    )
    return _Principal(user.id, user.institution_id, frozenset(r.value for r in roles), profile)


def _shorten_uuids(sql: str) -> str:
    """UUIDs are noise on a projector. Keep the first block so they stay distinguishable."""
    out = []
    for line in sql.splitlines():
        while True:
            start = line.find("'")
            if start == -1:
                break
            end = line.find("'", start + 1)
            if end == -1 or end - start != 37:
                break
            line = line[: start + 9] + "…'" + line[end + 1 :]
        out.append(line)
    return "\n".join(out)


async def _one_role(session: AsyncSession, label: str, email: str) -> None:
    scope: Scope = await scope_for(session, await _principal(session, email))
    guarded = guard(MODEL_SQL, scope, row_limit=500)
    columns, rows = await service._run_readonly(guarded.executed_sql)  # noqa: SLF001 — demo

    rule(f"SIGNED IN AS: {label}")
    print(_shorten_uuids(guarded.executed_sql))
    print(f"\n  -> {len(rows)} row{'' if len(rows) == 1 else 's'}")
    for row in rows[:3]:
        print("     " + " | ".join(str(value) for value in row))
    if len(rows) > 3:
        print(f"     … and {len(rows) - 3} more")


async def main() -> None:
    engine = create_async_engine(to_async_url(get_settings().database_url))
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    rule("ASK THE DATA — the same question, asked by three different people")
    print(textwrap.fill(f'The question: "{QUESTION}"', WIDTH))
    print("\nThe AI turns it into this. It is never told who is asking:\n")
    print("  " + MODEL_SQL)
    print("\nWatch what the platform does to it.")

    async with factory() as session:
        for label, email in CAST:
            await _one_role(session, label, email)

    rule("SAME QUERY. THREE ANSWERS. Nothing was passed in to say who was asking.")
    print("The highlighted WITH block redefines what 'student_360' means for that one")
    print("query, so the model's own SQL reads a different set of rows each time.")

    rule("WHAT IT REFUSES")
    async with factory() as session:
        scope = await scope_for(session, await _principal(session, CAST[0][1]))
    for label, sql in REFUSALS:
        try:
            guard(sql, scope)
        except GuardrailViolation as exc:
            print(f"\n  {label}")
            print(f"    {sql}")
            print(f"    REFUSED — {exc.reason}")
        else:
            print(f"\n  {label}\n    !! ALLOWED — this is a bug, please report it")

    rule("AND IF ALL OF THAT FAILED")
    print("The connection is put into read-only mode by PostgreSQL itself, with a 5s")
    print("timeout. A mistake anywhere above still cannot write to the database.")

    # Settings, not os.environ: the key normally arrives via backend/.env, which
    # pydantic-settings reads without exporting into the process environment.
    if get_settings().openrouter_configured:
        rule("LIVE — asking the real model")
        async with factory() as session:
            scope = await scope_for(session, await _principal(session, CAST[1][1]))
            answer = await service.answer_question(QUESTION, scope, row_limit=20)
        print(f'Question: "{answer.question}"  (as Meera)\n')
        if answer.answered:
            print("The model wrote:\n  " + (answer.model_sql or "").replace("\n", "\n  "))
            print(f"\n  -> {answer.row_count} rows")
        else:
            print(f"Not answered: {answer.reason}")
    else:
        rule("LIVE QUESTIONS")
        print("Set OPENROUTER_API_KEY in backend/.env to ask the real model. Everything")
        print("above runs without it — the boundary does not depend on the AI.")

    print()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

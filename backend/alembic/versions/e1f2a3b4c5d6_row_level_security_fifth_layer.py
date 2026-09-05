"""Row-Level Security — the 5th defense-in-depth layer, enforced inside Postgres itself.

Four independent app-layer scoping gaps have been found and fixed in this project so far
(Finding 4, and Finding 5's three tables) — each one invisible until someone specifically
tested the right question. Every one of those bugs lived in `apply_role_scope.py`, the
single Python function that rewrites a query's AST before it runs. RLS is what still holds
if that function has a bug nobody's found yet: enforcement happens inside Postgres itself,
regardless of what SQL text arrives or what actually connects to the database (this app, an
admin tool, a future script, a bug in `apply_role_scope.py` that skips a table entirely).

**Scope: mirrors `apply_role_scope.py` exactly, does not reinvent it.** Every table in
`STUDENT_SCOPED_TABLES`/`INSTITUTION_SCOPED_TABLES` (35 tables including all three
deferred-curriculum batches) gets a policy encoding the *same* rule that file already
implements and this project has already reviewed table-by-table. This migration is a
second, independent enforcement of an already-reviewed rule, not a place to design new
policy. `question_answer_keys` is deliberately excluded: it carries no grant at all for
`text_to_sql_reader` (see migration `c9d0e1f2a3b4`), so there is no row visibility to
restrict — `FOR SELECT USING (false)` is added anyway, for the same "don't depend on only
one layer" reasoning as everything else here, in case a future grant is ever added without
someone also remembering this table's total exclusion.

**Which role this targets, and why `education` doesn't need a policy.** `text_to_sql_reader`
(migration `c9d0e1f2a3b4`) is a plain role — `rolbypassrls = false`, `rolsuper = false`,
confirmed live — so every policy below actually constrains it. `education`, the app's own
role (used by `audit_log`, migrations, and everything outside the text-to-SQL pipeline), is
confirmed live to be a Postgres **superuser** in this environment (`rolsuper = true`) —
superusers always bypass RLS unconditionally, so `education` needs no policy and none of
this migration changes its behavior. That said, this is flagged, not silently relied on:
being a superuser is very likely a local-dev-container artifact (the bootstrap Postgres
user), not a deliberate production security decision, and a superuser can also disable RLS
outright or drop these policies — the exact "trusting only one layer" posture this whole
feature exists to avoid. `education` is explicitly granted `BYPASSRLS` below too, so its
exemption from these policies is an explicit, reviewable grant rather than something that
only holds by accident of its current superuser status. If `education` is ever demoted from
superuser (the right move for a real production posture), this grant is what keeps normal
app operations — CRUD outside the text-to-SQL path, migrations — working unaffected.

**Identity propagation.** Policies read three session variables — `app.current_user_id`,
`app.current_user_role`, `app.current_institution_id` — set via `SET LOCAL` (transaction-
scoped, not connection-scoped) by `execute_sql.py` at the start of the same transaction that
runs the query, sourced from the same `state["user_id"]`/`state["user_role"]`/
`state["institution_id"]` fields every other node already trusts — never from the question
or LLM output. `SET LOCAL`, not `SET`: on a pooled connection, `SET` would leak a value
across to a different session's next query on the same physical connection; `SET LOCAL`
resets at transaction end regardless of what happens to the connection afterward. The three
helper functions below (`app_current_user_id()`/`app_current_user_role()`/
`app_current_institution_id()`) all use `current_setting(name, true)` — the `true` "missing
is OK" flag — wrapped in `NULLIF(..., '')`, so an unset variable becomes SQL `NULL` rather
than raising an error. `NULL` never satisfies `=` against anything (including another
`NULL`), so a policy that never got its session variables set denies by default — zero rows,
not "everything," not a crash. This is the single most important property of every policy
below, and the missing-`SET LOCAL` case is the single most important test for this feature
(see the accompanying test file).

**Composability, and why these policies read shorter than `apply_role_scope.py`'s own
predicates for the same rule.** `apply_role_scope.py` must hand-assemble a full N-hop join
chain into one flat SQL string (`_institution_scoped_subquery` composing one hop at a time)
because it has no runtime enforcement layer beneath it to lean on — it IS the enforcement.
RLS does not have that constraint: once `topics` has its own policy, a *different* table's
policy that says `grade_subject_offering_id IN (SELECT id FROM grade_subject_offerings)`
gets that inner SELECT filtered by `grade_subject_offerings`' own policy automatically,
for the same querying role, every time, with no special-casing needed — confirmed live
(see the test file) rather than assumed from documentation. So most of the curriculum-chain
policies below are a single one-hop `IN (SELECT id FROM <parent>)`, not a hand-inlined
multi-join expression — this is a structural difference from the Python code, not a
different (weaker) rule. The parent table's own policy is what supplies the institution
boundary; nesting it again here would be redundant, not more correct.

**Composability's limit: it only holds when the parent's own policy is pure institution
membership, with no role predicate.** `topics IN (SELECT id FROM grade_subject_offerings)`
is safe because `grade_subject_offerings`' policy is institution-only — every row a query
could see there is exactly the institution boundary this line wants, nothing more. That
stops being true the moment the parent's *own* policy is role-dependent, which
`student_profiles`/`student_subject_enrollments`/`quiz_attempts` all are (self/taught/admin
branches, not just institution). Six policies below were originally written as the same
one-hop `IN (SELECT id FROM <parent>)` pattern against one of those three role-dependent
parents (`quiz_attempts`, `attendance_records`, `student_material_progress`,
`student_subject_enrollments`, `student_grade_enrollments`, `attempt_answers`) — found live,
via this migration's own cross-check test suite, to silently over-restrict:
`student_grade_enrollments` excluded a real row for a teacher that `apply_role_scope.py`
correctly included, because the inner `SELECT id FROM student_profiles` was already narrowed
to `app_teaches_student()`'s specific shape (an active subject enrollment matching a teaching
assignment) before this table's own, independently-correct EXISTS predicate (matching on
`period_grade_id`/`section_id` instead) ever ran — two conditions that are each right on their
own terms but not identical, so ANDing the parent's narrowed set on top silently loses rows
the app layer keeps. This is the opposite failure direction from the recursion bug above
(that one crashed; this one is RLS being *stricter* than the layer it's supposed to mirror,
found only because the test suite compares row-for-row rather than checking "some restriction
happened"). Fixed the same way as the recursion bug: `app_student_institution_id`/
`app_enrollment_institution_id`/`app_attempt_institution_id` (`SECURITY DEFINER`, see below)
read institution membership directly off the base table, bypassing that table's own RLS
entirely, so these six policies' institution-pin line is pure institution membership again —
matching what `apply_role_scope.py`'s own institution-pin logic actually checks — with the
role predicate carried entirely by each policy's own, separate `AND (...)` clause, exactly as
before.

**Where this necessarily diverges from `apply_role_scope.py`, and why.** `teaching_assignments`
in `_apply_row_scoping` special-cases only `role == "teacher"` (self-restrict) and
`role == "student"` (deny outright); any other role value — admin, or a hypothetical
unrecognized one — falls through with no extra predicate, i.e. institution-only. That means
the *current app-layer code* would treat an unrecognized role the same as admin for this one
table — a latent asymmetry, out of scope to fix here, but worth naming rather than silently
reproducing. RLS is supposed to be the fail-closed backstop, so this migration does *not*
mirror that specific permissiveness: the policy below only grants unrestricted-within-
institution access for `app_current_user_role() = 'admin'` by name, and denies (rather than
defaults to admin-like access) for anything that isn't `'admin'` or `'teacher'`-with-a-
matching-`teacher_user_id`. This is a deliberate, narrow, documented divergence in the
stricter direction — the whole point of a fifth layer is to not have the exact same blind
spot as the fourth.

**Column redaction (`quiz_releases.released_by_user_id`) is structurally out of reach for
RLS and is not attempted here.** RLS operates at row granularity — a policy can only decide
whether a *row* is visible, never redact one *column*'s value while keeping the rest of the
row. `quiz_releases`' policy below enforces the row's institution boundary (the part RLS
*can* do, and does, independently of `apply_role_scope.py`), exactly like every other
curriculum table. The column-level redaction of `released_by_user_id` for a non-self
teacher/student reader remains an app-layer-only guarantee (`_redact_identity_columns`/
`_find_redacted_column_misuse` in `apply_role_scope.py`) — RLS provides no second layer for
that specific protection, and this is a real, permanent limitation of the mechanism, not an
oversight: a direct query against Postgres as `text_to_sql_reader`, with `SET LOCAL`
correctly set, sees the *real* `released_by_user_id` value for any row its institution
boundary allows, same as before this migration. Documented here explicitly, and covered by
an explicit test asserting this is expected, not a regression.

**`student_360` needs one more thing beyond its base tables' policies: `security_invoker`.**
RLS cannot be enabled directly on a view at all (`ALTER TABLE student_360 ENABLE ROW LEVEL
SECURITY` errors outright — confirmed live, "this operation is not supported for views")
— so `student_360`'s row visibility can only come from the policies on the real tables its
query reads (`student_subject_enrollments`, `student_profiles`, and others it joins). That
alone turned out not to be sufficient, found the hard way, not anticipated: Postgres has a
documented rule that if a view is owned by a role with BYPASSRLS, RLS is not applied to the
tables it reads when the view is queried, *regardless of who is actually running the
query*. `student_360` is owned by `education`, and this same migration explicitly grants
`education` BYPASSRLS (see above) — so without a further fix, every row of `student_360`
would be visible to `text_to_sql_reader` unconditionally, silently defeating every one of
`student_profiles`'/`student_subject_enrollments`'/etc.'s own policies the moment they're
read through this view instead of directly. Caught by the same cross-check technique this
feature's own test suite is built on (comparing `apply_role_scope`'s result against RLS's
raw result for the identical identity): a teacher's `student_360` query included one extra
student — outside their specific-section grant — that a direct query against
`student_subject_enrollments` alone, same identity, correctly excluded. The fix is
`ALTER VIEW student_360 SET (security_invoker = true)` (Postgres 15+, confirmed available —
live `server_version` 16.15): this makes the view evaluate permissions *and* RLS as the
actual calling role, not the view's owner, closing the gap regardless of the owner's own
bypass status.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-09-03 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str | Sequence[str] | None = "e1f2a3b4c5d6"
down_revision: str | Sequence[str] | None = "d0e1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_READER_ROLE = "text_to_sql_reader"
_APP_ROLE = "education"

# ---------------------------------------------------------------------------------------
# Helper functions: the SQL-side equivalent of apply_role_scope.py reading
# state["user_id"]/state["user_role"]/state["institution_id"] from a single, trusted
# source. STABLE (not IMMUTABLE): the setting can change within a session; a plain SQL
# function body needs no elevated privileges since current_setting() is available to any
# role. NULLIF(..., '') over the `current_setting(name, true)` result is what turns an
# unset variable into a real SQL NULL instead of an empty string that could otherwise
# coincidentally compare equal to a NULLIF'd column somewhere -- NULL is the only value
# guaranteed to never satisfy `=` against anything, which is the fail-closed property
# every policy below depends on.
_HELPER_FUNCTIONS_SQL = """
CREATE FUNCTION app_current_user_id() RETURNS uuid
LANGUAGE sql STABLE AS $$
    SELECT NULLIF(current_setting('app.current_user_id', true), '')::uuid
$$;

CREATE FUNCTION app_current_user_role() RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT NULLIF(current_setting('app.current_user_role', true), '')
$$;

CREATE FUNCTION app_current_institution_id() RETURNS uuid
LANGUAGE sql STABLE AS $$
    SELECT NULLIF(current_setting('app.current_institution_id', true), '')::uuid
$$;

-- SECURITY DEFINER: runs with this function's owner's privileges (the migration-running
-- role, confirmed superuser/BYPASSRLS in this environment -- see the module docstring),
-- not the caller's -- so its internal reads of teaching_assignments/
-- student_subject_enrollments/student_grade_enrollments bypass RLS entirely rather than
-- re-triggering those tables' own policies. This isn't a convenience; it's required.
-- student_profiles' own policy needs to ask "does the current teacher teach this
-- student", and student_subject_enrollments'/student_grade_enrollments' policies both
-- independently need to read student_profiles for their own institution/self checks --
-- confirmed live that writing this as a plain cross-table subquery instead produces
-- Postgres error "infinite recursion detected in policy for relation student_profiles"
-- (two tables' policies each querying the other, a textbook RLS cycle, not a hypothetical
-- one). A SECURITY DEFINER function breaks the cycle at its source: student_profiles'
-- policy calls this function instead of touching student_subject_enrollments/
-- teaching_assignments/student_grade_enrollments directly, so nothing on that side ever
-- re-enters an RLS-evaluated read of student_profiles. Logic mirrors apply_role_scope.py's
-- own `_taught_student_ids_subquery` exactly -- an active teaching assignment whose
-- offering matches an active subject enrollment for this student, where a NULL
-- section_id grant covers every section of that offering.
CREATE FUNCTION app_teaches_student(p_student_id uuid) RETURNS boolean
LANGUAGE sql SECURITY DEFINER STABLE AS $$
    SELECT EXISTS (
        SELECT 1
        FROM teaching_assignments ta
        JOIN student_subject_enrollments sse
            ON sse.grade_subject_offering_id = ta.grade_subject_offering_id
            AND sse.status = 'active'
        LEFT JOIN student_grade_enrollments sge ON sge.id = sse.grade_enrollment_id
        WHERE ta.teacher_user_id = app_current_user_id()
            AND ta.status = 'active'
            AND sse.student_id = p_student_id
            AND (ta.section_id IS NULL OR ta.section_id = sge.section_id)
    )
$$;

-- SECURITY DEFINER raw institution lookups -- fixes a composability bug found via this
-- migration's own cross-check test suite (test_rls_matches_apply_role_scope_for_every_table,
-- student_grade_enrollments/teacher_user_id): a policy's "institution pin" line written as
-- `student_id IN (SELECT id FROM student_profiles)` does not just check institution
-- membership the way it reads -- student_profiles has its OWN role-dependent policy (admin:
-- all in institution, student: self only, teacher: only app_teaches_student() rows), so that
-- subquery is silently filtered down to whatever the CURRENT role/identity can already see
-- in student_profiles, before this table's own, separately-computed role predicate even runs.
-- For a teacher, app_teaches_student() (any active subject enrollment matching any teaching
-- assignment) and a table's own more specific EXISTS predicate (e.g.
-- student_grade_enrollments' period_grade_id/section_id match) are two independently-correct
-- but not-identical conditions -- a real row can satisfy the table's own EXISTS while failing
-- app_teaches_student()'s narrower shape, and the naive pin then excludes it even though
-- apply_role_scope.py (which has no such nested-RLS side effect -- Python subqueries don't
-- get re-filtered) correctly includes it. This is the opposite failure mode from the
-- infinite-recursion bug above: that one crashed; this one silently over-restricts, an RLS
-- policy being *stricter* than the app layer it's supposed to mirror. These three functions
-- read institution_id directly, bypassing student_profiles'/student_subject_enrollments'/
-- quiz_attempts' own RLS entirely (SECURITY DEFINER, same mechanism as app_teaches_student
-- above), so a policy's institution-pin line can be pure institution membership -- exactly
-- what apply_role_scope.py's own institution-pin logic checks -- with zero role-predicate
-- leakage from the parent table's policy.
CREATE FUNCTION app_student_institution_id(p_student_id uuid) RETURNS uuid
LANGUAGE sql SECURITY DEFINER STABLE AS $$
    SELECT institution_id FROM student_profiles WHERE id = p_student_id
$$;

CREATE FUNCTION app_enrollment_institution_id(p_enrollment_id uuid) RETURNS uuid
LANGUAGE sql SECURITY DEFINER STABLE AS $$
    SELECT sp.institution_id
    FROM student_subject_enrollments sse
    JOIN student_profiles sp ON sp.id = sse.student_id
    WHERE sse.id = p_enrollment_id
$$;

CREATE FUNCTION app_attempt_institution_id(p_attempt_id uuid) RETURNS uuid
LANGUAGE sql SECURITY DEFINER STABLE AS $$
    SELECT sp.institution_id
    FROM quiz_attempts qa
    JOIN student_subject_enrollments sse ON sse.id = qa.student_subject_enrollment_id
    JOIN student_profiles sp ON sp.id = sse.student_id
    WHERE qa.id = p_attempt_id
$$;
"""

_DROP_HELPER_FUNCTIONS_SQL = """
DROP FUNCTION IF EXISTS app_current_user_id();
DROP FUNCTION IF EXISTS app_current_user_role();
DROP FUNCTION IF EXISTS app_current_institution_id();
DROP FUNCTION IF EXISTS app_teaches_student(uuid);
DROP FUNCTION IF EXISTS app_student_institution_id(uuid);
DROP FUNCTION IF EXISTS app_enrollment_institution_id(uuid);
DROP FUNCTION IF EXISTS app_attempt_institution_id(uuid);
"""

# (table, USING expression) -- one policy per table, FOR SELECT only (text_to_sql_reader
# has no other grant), enabled for every role except the ones with an explicit BYPASSRLS
# grant below. Grouped to match apply_role_scope.py's own STUDENT_SCOPED_TABLES /
# INSTITUTION_SCOPED_TABLES / special-case ordering, not alphabetically, so this stays
# directly diffable against that file's own table classification.
_POLICIES: list[tuple[str, str]] = [
    # --- STUDENT_SCOPED_TABLES: institution pin + self/taught row predicate -----------
    (
        "student_profiles",
        # Teacher branch calls app_teaches_student() rather than joining
        # teaching_assignments/student_subject_enrollments/student_grade_enrollments
        # directly -- see that function's own comment for the infinite-recursion cycle
        # this avoids (those tables' own policies read student_profiles back).
        """
        institution_id = app_current_institution_id()
        AND (
            app_current_user_role() = 'admin'
            OR (app_current_user_role() = 'student' AND user_id = app_current_user_id())
            OR (app_current_user_role() = 'teacher' AND app_teaches_student(id))
        )
        """,
    ),
    (
        "quiz_attempts",
        """
        app_student_institution_id(student_id) = app_current_institution_id()
        AND (
            app_current_user_role() = 'admin'
            OR (
                app_current_user_role() = 'student'
                AND student_id IN (SELECT id FROM student_profiles WHERE user_id = app_current_user_id())
            )
            OR (
                app_current_user_role() = 'teacher'
                AND EXISTS (
                    SELECT 1
                    FROM student_subject_enrollments sse
                    JOIN teaching_assignments ta
                        ON ta.grade_subject_offering_id = sse.grade_subject_offering_id
                        AND ta.status = 'active'
                    LEFT JOIN student_grade_enrollments sge ON sge.id = sse.grade_enrollment_id
                    WHERE sse.id = quiz_attempts.student_subject_enrollment_id
                        AND ta.teacher_user_id = app_current_user_id()
                        AND (ta.section_id IS NULL OR ta.section_id = sge.section_id)
                )
            )
        )
        """,
    ),
    (
        "attendance_records",
        """
        app_student_institution_id(student_id) = app_current_institution_id()
        AND (
            app_current_user_role() = 'admin'
            OR (
                app_current_user_role() = 'student'
                AND student_id IN (SELECT id FROM student_profiles WHERE user_id = app_current_user_id())
            )
            OR (
                app_current_user_role() = 'teacher'
                AND EXISTS (
                    SELECT 1 FROM teaching_assignments ta
                    WHERE ta.teacher_user_id = app_current_user_id()
                        AND ta.status = 'active'
                        AND ta.grade_subject_offering_id = attendance_records.grade_subject_offering_id
                        AND (ta.section_id IS NULL OR ta.section_id = attendance_records.section_id)
                )
            )
        )
        """,
    ),
    (
        "student_material_progress",
        """
        app_enrollment_institution_id(student_subject_enrollment_id) = app_current_institution_id()
        AND (
            app_current_user_role() = 'admin'
            OR (
                app_current_user_role() = 'student'
                AND student_subject_enrollment_id IN (
                    SELECT id FROM student_subject_enrollments WHERE student_id IN (
                        SELECT id FROM student_profiles WHERE user_id = app_current_user_id()
                    )
                )
            )
            OR (
                app_current_user_role() = 'teacher'
                AND EXISTS (
                    SELECT 1
                    FROM student_subject_enrollments sse
                    JOIN teaching_assignments ta
                        ON ta.grade_subject_offering_id = sse.grade_subject_offering_id
                        AND ta.status = 'active'
                    LEFT JOIN student_grade_enrollments sge ON sge.id = sse.grade_enrollment_id
                    WHERE sse.id = student_material_progress.student_subject_enrollment_id
                        AND ta.teacher_user_id = app_current_user_id()
                        AND (ta.section_id IS NULL OR ta.section_id = sge.section_id)
                )
            )
        )
        """,
    ),
    (
        "student_subject_enrollments",
        """
        app_student_institution_id(student_id) = app_current_institution_id()
        AND (
            app_current_user_role() = 'admin'
            OR (
                app_current_user_role() = 'student'
                AND student_id IN (SELECT id FROM student_profiles WHERE user_id = app_current_user_id())
            )
            OR (
                app_current_user_role() = 'teacher'
                AND EXISTS (
                    SELECT 1 FROM teaching_assignments ta
                    LEFT JOIN student_grade_enrollments sge
                        ON sge.id = student_subject_enrollments.grade_enrollment_id
                    WHERE ta.teacher_user_id = app_current_user_id()
                        AND ta.status = 'active'
                        AND ta.grade_subject_offering_id = student_subject_enrollments.grade_subject_offering_id
                        AND (ta.section_id IS NULL OR ta.section_id = sge.section_id)
                )
            )
        )
        """,
    ),
    (
        "student_grade_enrollments",
        """
        app_student_institution_id(student_id) = app_current_institution_id()
        AND (
            app_current_user_role() = 'admin'
            OR (
                app_current_user_role() = 'student'
                AND student_id IN (SELECT id FROM student_profiles WHERE user_id = app_current_user_id())
            )
            OR (
                app_current_user_role() = 'teacher'
                AND EXISTS (
                    SELECT 1
                    FROM teaching_assignments ta
                    JOIN grade_subject_offerings gso ON gso.id = ta.grade_subject_offering_id
                    WHERE ta.teacher_user_id = app_current_user_id()
                        AND ta.status = 'active'
                        AND gso.period_grade_id = student_grade_enrollments.period_grade_id
                        AND (ta.section_id IS NULL OR ta.section_id = student_grade_enrollments.section_id)
                )
            )
        )
        """,
    ),
    (
        "attempt_answers",
        """
        app_attempt_institution_id(attempt_id) = app_current_institution_id()
        AND (
            app_current_user_role() = 'admin'
            OR (
                app_current_user_role() = 'student'
                AND attempt_id IN (
                    SELECT id FROM quiz_attempts WHERE student_id IN (
                        SELECT id FROM student_profiles WHERE user_id = app_current_user_id()
                    )
                )
            )
            OR (
                app_current_user_role() = 'teacher'
                AND EXISTS (
                    SELECT 1
                    FROM quiz_attempts qa
                    JOIN student_subject_enrollments sse ON sse.id = qa.student_subject_enrollment_id
                    JOIN teaching_assignments ta
                        ON ta.grade_subject_offering_id = sse.grade_subject_offering_id
                        AND ta.status = 'active'
                    LEFT JOIN student_grade_enrollments sge ON sge.id = sse.grade_enrollment_id
                    WHERE qa.id = attempt_answers.attempt_id
                        AND ta.teacher_user_id = app_current_user_id()
                        AND (ta.section_id IS NULL OR ta.section_id = sge.section_id)
                )
            )
        )
        """,
    ),
    # --- INSTITUTION_SCOPED_TABLES: plain institution pin -----------------------------
    ("institutions", "id = app_current_institution_id()"),
    ("users", "institution_id = app_current_institution_id()"),
    ("grades", "institution_id = app_current_institution_id()"),
    ("subjects", "institution_id = app_current_institution_id()"),
    ("academic_periods", "institution_id = app_current_institution_id()"),
    (
        "period_grades",
        "academic_period_id IN (SELECT id FROM academic_periods)",
    ),
    (
        "sections",
        "period_grade_id IN (SELECT id FROM period_grades)",
    ),
    (
        "grade_subject_offerings",
        "period_grade_id IN (SELECT id FROM period_grades)",
    ),
    # --- INSTITUTION_SCOPED_TABLES special cases ---------------------------------------
    (
        "user_roles",
        """
        user_id IN (SELECT id FROM users)
        AND (app_current_user_role() = 'admin' OR user_id = app_current_user_id())
        """,
    ),
    (
        "refresh_sessions",
        """
        user_id IN (SELECT id FROM users)
        AND (app_current_user_role() = 'admin' OR user_id = app_current_user_id())
        """,
    ),
    (
        "teaching_assignments",
        # Deliberately diverges from apply_role_scope.py's own fallthrough for an
        # unrecognized role -- see the module docstring's "Where this necessarily
        # diverges" section. Only a role that is confidently 'admin' gets the
        # institution-wide reading; anything else needs a matching teacher_user_id.
        """
        academic_period_id IN (SELECT id FROM academic_periods)
        AND (
            app_current_user_role() = 'admin'
            OR (app_current_user_role() = 'teacher' AND teacher_user_id = app_current_user_id())
        )
        """,
    ),
    # --- Curriculum-content tables (Batches 1-3): institution pin via FK chain,
    # composed through each parent's own policy rather than re-inlined (see the module
    # docstring's "Composability" section). -------------------------------------------
    (
        "topics",
        "grade_subject_offering_id IN (SELECT id FROM grade_subject_offerings)",
    ),
    ("subtopics", "topic_id IN (SELECT id FROM topics)"),
    ("learning_outcomes", "subtopic_id IN (SELECT id FROM subtopics)"),
    ("source_materials", "subtopic_id IN (SELECT id FROM subtopics)"),
    ("questions", "subtopic_id IN (SELECT id FROM subtopics)"),
    (
        "common_mastery_quizzes",
        """
        (subtopic_id IS NOT NULL AND subtopic_id IN (SELECT id FROM subtopics))
        OR (topic_id IS NOT NULL AND topic_id IN (SELECT id FROM topics))
        """,
    ),
    (
        "source_material_versions",
        "source_material_id IN (SELECT id FROM source_materials)",
    ),
    ("question_versions", "question_id IN (SELECT id FROM questions)"),
    ("quiz_versions", "quiz_id IN (SELECT id FROM common_mastery_quizzes)"),
    (
        "source_chunks",
        "source_material_version_id IN (SELECT id FROM source_material_versions)",
    ),
    ("question_options", "question_version_id IN (SELECT id FROM question_versions)"),
    (
        "quiz_items",
        """
        quiz_version_id IN (SELECT id FROM quiz_versions)
        AND question_version_id IN (SELECT id FROM question_versions)
        """,
    ),
    (
        "quiz_material_bindings",
        """
        quiz_version_id IN (SELECT id FROM quiz_versions)
        AND source_material_version_id IN (SELECT id FROM source_material_versions)
        """,
    ),
    (
        "question_outcome_tags",
        """
        question_version_id IN (SELECT id FROM question_versions)
        AND learning_outcome_id IN (SELECT id FROM learning_outcomes)
        """,
    ),
    (
        "quiz_releases",
        # Row-level institution boundary only -- see the module docstring's "Column
        # redaction" section for why released_by_user_id's per-column redaction has no
        # RLS equivalent and remains app-layer-only.
        "quiz_version_id IN (SELECT id FROM quiz_versions)",
    ),
    # --- Never readable at all, regardless of grants (defense-in-depth for a future
    # accidental grant on this table -- see the module docstring). ---------------------
    ("question_answer_keys", "false"),
]


def upgrade() -> None:
    op.execute(_HELPER_FUNCTIONS_SQL)

    for table, using_expr in _POLICIES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_rls_select ON {table} "
            f"FOR SELECT USING ({using_expr})"
        )

    # Explicit, reviewable bypass for the app's own full-privilege role -- not solely
    # dependent on it remaining a Postgres superuser. See the module docstring's
    # "Which role this targets" section.
    op.execute(f"ALTER ROLE {_APP_ROLE} BYPASSRLS")

    # Without this, student_360 -- owned by _APP_ROLE, just granted BYPASSRLS above --
    # would silently skip RLS on every table it reads, regardless of who queries the
    # view. See the module docstring's own section on this for the live evidence that
    # found it. Must run after the BYPASSRLS grant above conceptually (it's the grant
    # that creates the gap this closes), though DDL ordering here doesn't actually
    # matter -- both take effect only once the transaction commits.
    op.execute("ALTER VIEW student_360 SET (security_invoker = true)")


def downgrade() -> None:
    op.execute("ALTER VIEW student_360 RESET (security_invoker)")
    op.execute(f"ALTER ROLE {_APP_ROLE} NOBYPASSRLS")

    for table, _using_expr in _POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {table}_rls_select ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.execute(_DROP_HELPER_FUNCTIONS_SQL)

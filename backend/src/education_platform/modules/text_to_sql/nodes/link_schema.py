"""Narrows state["schema_context"]'s per-table listings to the tables a specific
question is actually likely to need, between load_schema and generate_sql.

Why this exists: load_schema hands the *entire* filtered catalog to generate_sql on
every question, regardless of relevance — measured at 13,181 tokens (o200k_base, the
gpt-4o-mini tokenizer generate_sql actually uses) as of the Batch-3 curriculum-table
work, with the Table Catalog section (§2) alone accounting for 8,723 of those (66%)
across 35 tables. Sent unconditionally, on every question, including every retry. This
node cuts that down to the tables a question plausibly touches, via keyword matching
against real schema vocabulary (table/column names) rather than an embedding model —
see the design rationale below for why.

Read-only with respect to identity: this node reads `state["question"]` and
`state["schema_context"]` only, nothing else — no `user_id`/`user_role`/
`institution_id`. This is purely a topic-relevance narrowing, not a security boundary;
apply_role_scope remains the only place identity-based access decisions are made. A bug
here can make generate_sql produce a worse or refused query (a correctness/UX problem);
it cannot make apply_role_scope, validate_sql, or execute_sql behave any less strictly,
because none of them read schema_context at all — validate_sql's authority comes from
`load_schema.REQUIRED_TABLES` and live SQLAlchemy metadata, checked independently of
whatever the LLM's prompt happened to contain (confirmed by reading validate_sql.py: it
imports REQUIRED_TABLES directly, never state["schema_context"]). So a narrowing bug
here is bounded to "generate_sql might write a worse query" — it is structurally unable
to let anything through that validate_sql/apply_role_scope would otherwise have caught.

Keyword/rule-based matching, not embeddings: with only 35 tables (load_schema.
REQUIRED_TABLES) and schema names chosen to be descriptive by design (`quiz_releases`,
`common_mastery_quizzes`, `teaching_assignments` — "mastery" is literally in that table
name), lexical matching against table/column vocabulary covers the retrieval problem
well without an extra per-question API call, added latency, non-determinism, or vector
infrastructure. Confirmed against all 54 golden-eval questions (see
test_text_to_sql_link_schema.py's real-data recall test) rather than assumed.

False negatives (excluding a table the question actually needed) are a correctness
regression, not an acceptable cost tradeoff. Getting this right took real tuning against
real evidence, not a single guess that happened to work — worth recording honestly:

- First cut: FK-column names counted toward a table's vocabulary, and closure ran 2
  hops. Measured (not assumed): the single word "grade" alone, present in FK columns
  like `grade_subject_offering_id`/`period_grade_id` across many otherwise-unrelated
  tables, seeded 11 of 34 tables before closure even ran, which then reached ~29 tables
  after 2-hop closure — the opposite of this node's purpose. Root cause: an FK column
  matching a word means this table *references* something relevant, not that it *is*
  something relevant — and the table it references already gets pulled in by closure on
  its own merits. Fixed by excluding FK-typed columns (Type field contains "(FK") from
  `_table_vocabulary` entirely; only the table name and non-FK column names (`email`,
  `score_percent`, `passed`) count.
- Second cut, after that fix: 0-hop and 1-hop closure both produced real false negatives
  when checked against all 54 golden-eval questions' actual recorded `validated_sql` (34
  of the 54 have real ground truth to check against) — `teaching_assignments` was
  missing from questions like "How many students do I teach in total?" (the verb "teach"
  doesn't lexically match the table name "teaching_assignments" under this node's simple
  pluralization-only normalization) in the large majority of "my students" phrasings, and
  `academic_periods` was missing from "this term" phrasings the same way, for the same
  reason `student_360` was already called out as needing default inclusion: both are as
  structurally cross-cutting for teacher/student-scoped questions as `student_360` is —
  confirmed by schema_catalog.md §1's own Multi-tenancy bullet, which groups `grades`/
  `subjects`/`academic_periods` alongside `users`/`student_profiles` as the tables
  institution_id lives directly on. Adding `teaching_assignments`, `academic_periods`,
  and `subjects` to `_ALWAYS_INCLUDED_TABLES` (subjects for the same reason — a question
  naming a subject by value, "Mathematics"/"Science", without ever saying the word
  "subject", was the last remaining false-negative pattern) and reducing closure to 1 hop
  (no longer needed at 2 once these hubs aren't dependent on lucky keyword seeding)
  brought real, measured recall to 0 false negatives across all 34 ground-truth rows,
  averaging 17.6 of 34 tables selected (52%). Table *count* reduction is larger than
  token reduction, though: a table's column-listing rows vary a lot in size, and the
  always-included/closure-pulled tables tend to be the bigger ones, so the actual
  average narrowed-context size is 9,414 of 13,181 tokens (71% — a real, but more
  modest, ~29% average reduction; an earlier measurement of this same tuning reported
  45%/5,979 before a section-scoping bug in the text-reconstruction step — see below —
  was found and fixed, which had been silently deleting content and making the
  narrowed output look smaller than it actually was; corrected here rather than left
  overstated) — see test_text_to_sql_link_schema.py's real-data recall test, which
  re-runs the recall half of this check as a regression guard.
- Third cut: `_narrow_enum_reference`/`_narrow_fk_relationships` initially ran their
  row-filtering regex across the *entire* reconstructed document rather than scoped to
  their own section's boundaries. `_ENUM_ROW_RE`'s pattern (any pipe-delimited row
  starting with a single backtick-quoted word) is generic enough to also match §2's own
  column-definition rows once applied
  document-wide, and did: every kept table's column rows were being silently deleted
  (their Type field, e.g. `Uuid`, never names a selected table), caught by
  test_link_schema_preserves_always_kept_sections_verbatim failing on completely
  unrelated content far down the document. Fixed by slicing out each section's own
  substring, filtering only that slice, and splicing the result back — never a
  whole-document regex substitution for either section.
- Remaining defense, for whatever this measured tuning still doesn't cover: if keyword
  matching selects nothing at all (a question with no lexical overlap with any table/
  column name — genuinely off-topic, or phrased in a way this matcher doesn't
  recognize), this node returns the *original, unnarrowed* schema_context rather than an
  empty or near-empty one. An unnarrowed context is exactly today's behavior — never
  worse than what generate_sql already gets without this node at all.

What narrows and what never does: only §2 Table Catalog, §3 Enum Reference (rows whose
Column(s) field names a selected table), and §4 Foreign Key Relationships (lines where
either side is a selected table — kept because a join line is only useful alongside the
tables it connects, and dropping it while keeping the table would strand generate_sql
without the join path). Everything else — the document header, §1 Conventions, §5
student_360 (always-included per above, not merely a narrowing survivor), §6 Glossary,
§7 Query Notes & Gotchas — is cross-cutting and always kept in full, verbatim,
regardless of which tables get selected; these sections are what the module docstring
calls "patterns that apply across every table," so narrowing them per-question would be
narrowing the wrong axis entirely.

Runs once, on the first pass only — like load_schema, this node sits before
generate_sql's retry loop in graph.py (a validate_sql retry edge goes straight back to
generate_sql, not through this node), so a narrowed-but-insufficient context is not
something a retry can widen; the fail-safe empty-match fallback and the generous closure
radius are this node's own defense against that, not something deferred to a later
retry.
"""

from __future__ import annotations

import re
from typing import Final

from education_platform.modules.text_to_sql.nodes.load_schema import REQUIRED_TABLES
from education_platform.modules.text_to_sql.state import TextToSQLState

# Rounds of "add any table one FK hop from a currently-selected table" to run after the
# initial keyword match. Tuned against real golden-eval recall — see the module
# docstring's tuning history for why 1, not the 2 this started at.
_CLOSURE_HOPS: Final[int] = 1

# Tables kept in the narrowed context unconditionally, regardless of keyword match — see
# the module docstring's tuning history for why each of these four earned a place here
# (student_360 by explicit design requirement; the other three from measured golden-eval
# false negatives). A future broadly-applicable table/view earns its way in here the same
# deliberate, individually-reviewed way this project's other allow/deny lists work, not
# by silent default.
_ALWAYS_INCLUDED_TABLES: Final[frozenset[str]] = frozenset(
    {"student_360", "teaching_assignments", "academic_periods", "subjects"}
)

# Vocabulary words shorter than this are dropped from both the question's word set and
# each table's vocabulary before matching — short fragments ("id", "at", "is") match far
# too much of both natural language and column-name suffixes to carry any real signal.
_MIN_WORD_LENGTH: Final[int] = 4

_TABLE_BLOCK_RE = re.compile(r"#### `(\w+)`\n(.*?)(?=\n#### |\n---\n)", re.DOTALL)
_COLUMN_ROW_RE = re.compile(
    r"^\| `([a-zA-Z0-9_]+(?: */ *`[a-zA-Z0-9_]+`)*)` \| ([^|]+) \|", re.MULTILINE
)
_ENUM_ROW_RE = re.compile(r"^(\| `\w+` \| )(.+?)( \| .*\|)$", re.MULTILINE)
_FK_LINE_RE = re.compile(r"^(\w+)\.\w+\s+references\s+(\w+)\.", re.MULTILINE)
_TABLE_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")


def _words(text: str) -> set[str]:
    """Lowercase word tokens, each also contributing a naive singular form (a trailing
    `s` stripped) so "teachers"/"teacher", "sessions"/"session" etc. match across the
    plural/singular boundary without a real stemmer — deliberately simple, matching this
    node's overall "rule-based over ML" posture.
    """
    raw = {tok.lower() for tok in _TABLE_TOKEN_RE.findall(text)}
    out: set[str] = set()
    for word in raw:
        out.add(word)
        if word.endswith("s") and len(word) > _MIN_WORD_LENGTH:
            out.add(word[:-1])
    return {w for w in out if len(w) >= _MIN_WORD_LENGTH}


def _table_vocabulary(table_name: str, block_body: str) -> set[str]:
    """Every word worth matching against for this table: the table name's own
    underscore-split words, plus every *non-FK* column name's underscore-split words (a
    column can be documented as `a` / `b` for two similarly-typed columns sharing one
    row, per schema_catalog.md's own convention — both sides are captured).

    FK columns (Type field contains "(FK") are deliberately excluded here: a column
    like `grade_subject_offering_id` matching the word "grade" doesn't mean this table
    is *about* grades, only that it references a table that is — and that table already
    gets pulled in by `_parse_fk_graph`'s closure step regardless. Including FK column
    names in vocabulary was tried and measured: "grade" alone, via FK columns named
    `grade_subject_offering_id`/`period_grade_id`, matched 11 of 34 tables before any
    closure even ran, which then exploded to ~29 tables after 2-hop closure — the
    opposite of what this node exists to do. Non-FK columns don't have this problem:
    they describe what a table *is* (`email`, `score_percent`, `passed`), not what it
    *points at*.
    """
    vocab = _words(table_name)
    for match in _COLUMN_ROW_RE.finditer(block_body):
        name, col_type = match.group(1), match.group(2)
        if "(FK" in col_type:
            continue
        vocab |= _words(name)
    return vocab


def _parse_table_blocks(schema_context: str) -> dict[str, str]:
    """table_name -> its full `#### \\`table_name\\` ...` block (header line included),
    for every table block in §2 — same delimiting pattern load_schema.py's own
    `_remove_table_block` uses, so this parses exactly what that function would remove.
    """
    blocks: dict[str, str] = {}
    for match in _TABLE_BLOCK_RE.finditer(schema_context):
        name, body = match.group(1), match.group(2)
        blocks[name] = f"#### `{name}`\n{body}"
    return blocks


def _parse_fk_graph(schema_context: str) -> dict[str, set[str]]:
    """Undirected adjacency: table -> set of tables one FK hop away (either direction of
    `A.col references B.id`), parsed from §4 — the same flat FK-edge list
    `_institution_predicate_sql`'s one-hop composition already trusts as ground truth,
    reused here rather than re-deriving join paths from the ORM a second way.
    """
    graph: dict[str, set[str]] = {}
    for match in _FK_LINE_RE.finditer(schema_context):
        a, b = match.group(1), match.group(2)
        graph.setdefault(a, set()).add(b)
        graph.setdefault(b, set()).add(a)
    return graph


def _select_tables(question: str, schema_context: str) -> set[str] | None:
    """The narrowed table set for `question`, or `None` if keyword matching found no
    match at all (caller falls back to the full, unnarrowed context — see the module
    docstring's fail-safe point).
    """
    question_words = _words(question)
    if not question_words:
        return None

    table_blocks = _parse_table_blocks(schema_context)
    selected = {
        name
        for name, body in table_blocks.items()
        if _table_vocabulary(name, body) & question_words
    }
    if not selected:
        return None

    fk_graph = _parse_fk_graph(schema_context)
    for _ in range(_CLOSURE_HOPS):
        frontier = {
            neighbor
            for table in selected
            for neighbor in fk_graph.get(table, ())
            if neighbor in table_blocks
        }
        if frontier <= selected:
            break
        selected |= frontier

    return selected | (_ALWAYS_INCLUDED_TABLES & table_blocks.keys())


def _narrow_table_catalog(schema_context: str, selected: set[str]) -> str:
    table_blocks = _parse_table_blocks(schema_context)
    ordered = [name for name in table_blocks if name in selected]
    body = "\n\n".join(table_blocks[name] for name in ordered)
    header_end = schema_context.index("## 2. Table Catalog")
    section_end = schema_context.index("## 3. Enum Reference")
    return (
        schema_context[:header_end]
        + "## 2. Table Catalog\n\n"
        + "Narrowed to the tables this question's schema-linking step selected as "
        "relevant (see below for the full catalog's actual scope, unaffected by this "
        "narrowing).\n\n"
        + body
        + "\n\n---\n\n"
        + schema_context[section_end:]
    )


def _narrow_enum_reference(schema_context: str, selected: set[str]) -> str:
    """Filters §3 Enum Reference rows to only those whose Column(s) field names a
    selected table -- scoped strictly to the §3 substring (sliced out, filtered,
    spliced back), never a whole-document regex substitution. `_ENUM_ROW_RE`'s pattern
    (any `| \\`word\\` | ... | ... |` row) is generic enough to also match §2's own
    column-definition rows if applied document-wide -- confirmed the hard way: an
    earlier version of this function ran the same substitution across the entire
    narrowed context and silently gutted every kept table's column rows too (their Type
    field, e.g. `Uuid`, has no selected-table name in it, so `_keep` deleted them),
    caught by test_link_schema_preserves_always_kept_sections_verbatim failing on
    completely unrelated content further down the document. Scoping to the real section
    boundaries is what makes "only §2/§3/§4 narrow, nothing else does" actually true.
    """
    start = schema_context.index("## 3. Enum Reference")
    end = schema_context.index("## 4. Foreign Key Relationships")
    section = schema_context[start:end]

    def _keep(match: re.Match[str]) -> str:
        columns_field = match.group(2)
        tables_in_row = {name.split(".", 1)[0] for name in re.findall(r"`([\w.]+)`", columns_field)}
        return match.group(0) if tables_in_row & selected else ""

    narrowed_section = _ENUM_ROW_RE.sub(_keep, section)
    return schema_context[:start] + narrowed_section + schema_context[end:]


def _narrow_fk_relationships(schema_context: str, selected: set[str]) -> str:
    """Same section-scoping discipline as `_narrow_enum_reference`, for the same
    reason: §4's own FK-line pattern is specific enough that it's unlikely to
    accidentally match prose elsewhere, but "unlikely" isn't the bar a narrowing
    mechanism that must never corrupt content outside its own section should be held
    to -- sliced, filtered, spliced back, not a whole-document scan.
    """
    start = schema_context.index("## 4. Foreign Key Relationships")
    end = schema_context.index("## 5. Derived View")
    section = schema_context[start:end]

    lines = section.splitlines(keepends=True)
    out: list[str] = []
    for line in lines:
        match = _FK_LINE_RE.match(line)
        if match and not ({match.group(1), match.group(2)} & selected):
            continue
        out.append(line)
    narrowed_section = "".join(out)
    return schema_context[:start] + narrowed_section + schema_context[end:]


async def link_schema(state: TextToSQLState) -> TextToSQLState:
    schema_context = state.get("schema_context")
    question = state.get("question")
    if not schema_context or not question:
        # Nothing to narrow (load_schema failed upstream, or this node was invoked
        # directly without a question) -- leave state untouched, same "don't invent
        # behavior for a state shape that shouldn't reach this node" posture as
        # apply_role_scope's own missing-validated_sql guard. graph.py only reaches
        # this node via load_schema's "ok" edge, which guarantees schema_context.
        return {**state}

    selected = _select_tables(question, schema_context)
    if selected is None:
        # Fail-safe: no lexical signal at all -- ship the full, unnarrowed context,
        # identical to this node not existing. Never worse than today's behavior.
        return {
            **state,
            "audit_entry": {
                **(state.get("audit_entry") or {}),
                "schema_linking_tables_selected": None,
            },
        }

    narrowed = _narrow_table_catalog(schema_context, selected)
    narrowed = _narrow_enum_reference(narrowed, selected)
    narrowed = _narrow_fk_relationships(narrowed, selected)

    return {
        **state,
        "schema_context": narrowed,
        "audit_entry": {
            **(state.get("audit_entry") or {}),
            "schema_linking_tables_selected": sorted(selected),
        },
    }

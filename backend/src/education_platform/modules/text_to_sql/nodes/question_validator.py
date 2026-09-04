"""Second node in the graph, right after `injection_guard`: refuses a question that has
nothing to do with a school's students, grades, attendance, or curriculum at all — "what's
the weather", "write me a poem" — before any SQL is even attempted.

**This is a cost/UX layer, exactly like `injection_guard`, not a security boundary.** An
off-topic question was never a data-exposure risk: `apply_role_scope` doesn't care what a
query is "about," it only ever restricts one that was actually generated. What this node
buys is avoiding a wasted `generate_sql` round-trip (and, worse, a technically-valid but
pointless query against some in-schema table) for a question that was never going to
produce a meaningful answer, plus a distinct, honest audit signal instead of lumping this
in with an ordinary answered-or-refused query.

**Why this is its own node with its own classifier call, not folded into
`injection_guard`'s — this was tried, measured, and reverted.** Combining both checks into
`injection_guard`'s single classifier call (returning `{injection, off_topic, reason}`
instead of a second OpenRouter round-trip) shipped first, on the recommendation that it
was safe *if* combined-call accuracy matched a separate-call baseline — a comparison that
was never actually run before it shipped. Run afterward, on a batch built from the golden
eval set's injection rows (35, 36, 38), a representative set of off-topic questions, and
a set of legitimate in-domain questions including deliberately blunt phrasing:

- Injection dimension: both designs scored 3/3 hit rate with zero false positives —
  not in question, not what this section is about.
- Off-topic dimension, first pass (single run each): both scored 8/8 hit rate; combined
  had 1 false positive out of 10 legitimate questions ("What subject do I teach?" flagged
  `off_topic: true`), separate had 0/10 (its one extra flag landed on an injection case
  already correctly blocked for the right reason — no production impact either way).
- One data point isn't enough to call that a real gap rather than LLM variance, so the
  specific miss was re-run 8 times: **8/8, a 100% reproducible false positive** under the
  combined prompt. The rest of the same question shape (golden eval rows 16-18 — "what
  sections am I assigned to", "what is my own attendance rate", "am I currently teaching
  Grade 7") stayed clean at 0/5 each under the combined prompt, and the other 9 legitimate
  questions stayed clean at 0/3 each (13 legit questions, 50 combined-prompt calls total:
  8 false positives, all on the one phrasing). So this was not a systematic weakness for
  self-reference/teacher-identity questions as a category — it was a real, deterministic
  failure on one common phrasing, most likely because "subject" is genuinely overloaded in
  English (a school subject vs. the topic of a conversation), and a classifier explicitly
  primed to judge topical relevance reads the word in the wrong sense. The separate,
  off-topic-only prompt below got this exact question right in the original pass.

A common question failing 100% of the time in production is a real, recurring bad user
experience, not the marginal cost the combined design was supposed to be trading for — so
the calls are split back out. `injection_guard.py` is back to its original,
injection-only classifier; this node owns off-topic detection with its own call, using a
prompt written at the same style/quality as the reverted combined one (not a weaker
strawman), so the comparison that led here isolates "combined vs. separate," not "prompt
quality."

**No heuristic stage, unlike `injection_guard`.** There is no zero-cost regex equivalent
for "is this on topic" the way there is for adversarial phrasing tells — every question
that reaches this node pays for one classifier call. Same fail-open/fail-closed asymmetry
as `injection_guard`: unconfigured means an off-topic question simply isn't caught
(degrades to the prior, no-check-at-all behavior, not an outage); a classifier error fails
closed under its own `OFF_TOPIC_REJECTED` category, reusing `injection_guard`'s own
"safety check unavailable" wording for the message since the user-facing fact is the
same, but keeping the category this node's own — an infra failure here has nothing to do
with injection, and tagging it `INJECTION_BLOCKED` would misrepresent the audit trail for
a node that never touches that check at all.
"""

from __future__ import annotations

import json
from typing import Final

from pydantic import BaseModel, ConfigDict, ValidationError

from education_platform.core.config import get_settings
from education_platform.modules.assistant.openrouter import OpenRouterError, chat_completion_json
from education_platform.modules.text_to_sql.state import (
    OFF_TOPIC_REJECTED,
    TextToSQLState,
    format_error,
)

_OFF_TOPIC_REPLY: Final[str] = (
    "I can only help with questions about your school's students, classes, attendance, "
    "or curriculum data. Try asking something in that scope."
)
_GUARD_UNAVAILABLE_REPLY: Final[str] = (
    "This request's safety check is unavailable right now — please try again shortly."
)

# Written at the same style/quality as injection_guard's own prompt -- measured clean
# (8/8 hit rate, 0/10 false positives on legitimate questions, including the exact
# "What subject do I teach?" phrasing the combined prompt failed on) before this node
# was built. See this module's own docstring for the full comparison.
_CLASSIFIER_SYSTEM_PROMPT: Final[str] = (
    "You are a topic-relevance classifier in front of a text-to-SQL data assistant for "
    'a school. Return JSON {"off_topic": true|false, "reason": "..."}. Set "off_topic" '
    "for a question that has nothing to do with a school's students, grades, "
    "attendance, or curriculum data at all (e.g. the weather, general trivia, writing a "
    "poem, unrelated coding help). Do not set \"off_topic\" for a question that is "
    "merely blunt, broad, vague, or oddly phrased but still about school data — a "
    "genuinely ambiguous in-domain question should not be flagged. Default to false "
    "when in doubt."
)


class _OffTopicClassifierResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    off_topic: bool
    reason: str = ""


async def question_validator(state: TextToSQLState) -> TextToSQLState:
    question = state.get("question") or ""

    settings = get_settings()
    if not settings.openrouter_configured:
        # Fail open -- see module docstring's fail-open/fail-closed section.
        return {**state}

    try:
        data = await chat_completion_json(
            [
                {"role": "system", "content": _CLASSIFIER_SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            settings=settings,
        )
        classified = _OffTopicClassifierResult.model_validate(data)
    except (OpenRouterError, json.JSONDecodeError, TypeError, ValidationError):
        # Fail closed under this node's own category -- see module docstring.
        return {
            **state,
            "error": format_error(OFF_TOPIC_REJECTED, _GUARD_UNAVAILABLE_REPLY),
        }

    if classified.off_topic:
        return {
            **state,
            "error": format_error(OFF_TOPIC_REJECTED, _OFF_TOPIC_REPLY),
        }

    return {**state}

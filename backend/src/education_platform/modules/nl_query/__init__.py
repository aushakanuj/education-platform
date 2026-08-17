"""Ask-the-data: English question in, governed SQL out."""

from education_platform.modules.nl_query.guardrail import GuardrailViolation, guard
from education_platform.modules.nl_query.service import answer_question

__all__ = ["GuardrailViolation", "answer_question", "guard"]

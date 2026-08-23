"""Escape hatch reached when validate_sql can't produce valid SQL within MAX_RETRIES
attempts. Will set state["natural_answer"] to an explicit "can't answer this" message
rather than guessing. Not yet implemented.
"""

from __future__ import annotations

from education_platform.modules.text_to_sql.state import TextToSQLState


async def honest_refusal(state: TextToSQLState) -> TextToSQLState:
    """Placeholder — passes state through unchanged."""
    return state

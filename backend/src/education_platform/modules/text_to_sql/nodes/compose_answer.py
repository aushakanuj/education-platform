"""Will turn state["query_result"] into state["natural_answer"], with state["provenance"]
describing what was queried. Not yet implemented.
"""

from __future__ import annotations

from education_platform.modules.text_to_sql.state import TextToSQLState


async def compose_answer(state: TextToSQLState) -> TextToSQLState:
    """Placeholder — passes state through unchanged."""
    return state

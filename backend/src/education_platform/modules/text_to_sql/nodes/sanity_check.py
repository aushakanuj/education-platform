"""Will inspect state["query_result"] for anomalies (empty results, suspiciously large
diffs, etc.) that graph.py's routing after this node uses to pick a confidence level.
Not yet implemented.
"""

from __future__ import annotations

from education_platform.modules.text_to_sql.state import TextToSQLState


async def sanity_check(state: TextToSQLState) -> TextToSQLState:
    """Placeholder — passes state through unchanged."""
    return state

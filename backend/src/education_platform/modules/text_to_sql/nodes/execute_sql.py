"""Will run the role-scoped SQL and populate state["query_result"] /
state["result_row_count"]. Not yet implemented.
"""

from __future__ import annotations

from education_platform.modules.text_to_sql.state import TextToSQLState


async def execute_sql(state: TextToSQLState) -> TextToSQLState:
    """Placeholder — passes state through unchanged."""
    return state

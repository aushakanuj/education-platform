"""Will write state["audit_entry"] (question, SQL, role, outcome, timestamps, ...),
likely persisted via the `audit` module's audit_events table. Runs after both
compose_answer and honest_refusal, so refusals are logged too. Not yet implemented.
"""

from __future__ import annotations

from education_platform.modules.text_to_sql.state import TextToSQLState


async def audit_log(state: TextToSQLState) -> TextToSQLState:
    """Placeholder — passes state through unchanged."""
    return state

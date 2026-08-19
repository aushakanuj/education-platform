"""Central authorization: one place that answers "what may this person see?"."""

from education_platform.modules.authorization.scope import (
    Scope,
    scope_for,
)

__all__ = ["Scope", "scope_for"]

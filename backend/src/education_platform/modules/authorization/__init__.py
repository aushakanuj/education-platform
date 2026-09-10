"""Central authorization: one place that answers "what may this person see?"."""

from education_platform.modules.authorization.principal import Principal
from education_platform.modules.authorization.scope import Scope, scope_for

__all__ = ["Principal", "Scope", "scope_for"]

"""Text-to-SQL pipeline nodes. Each module holds one graph node; see graph.py for wiring.

All nine nodes (schema loading, SQL generation/validation, role scoping, execution,
sanity checking, answer composition, honest refusal, and audit logging) are implemented;
see each module's own docstring for its specific behavior and design decisions.
"""

from education_platform.modules.text_to_sql.nodes.apply_role_scope import (
    apply_role_scope as apply_role_scope,
)
from education_platform.modules.text_to_sql.nodes.audit_log import audit_log as audit_log
from education_platform.modules.text_to_sql.nodes.compose_answer import (
    compose_answer as compose_answer,
)
from education_platform.modules.text_to_sql.nodes.execute_sql import execute_sql as execute_sql
from education_platform.modules.text_to_sql.nodes.generate_sql import generate_sql as generate_sql
from education_platform.modules.text_to_sql.nodes.honest_refusal import (
    honest_refusal as honest_refusal,
)
from education_platform.modules.text_to_sql.nodes.load_schema import load_schema as load_schema
from education_platform.modules.text_to_sql.nodes.sanity_check import (
    sanity_check as sanity_check,
)
from education_platform.modules.text_to_sql.nodes.validate_sql import (
    validate_sql as validate_sql,
)

__all__ = [
    "apply_role_scope",
    "audit_log",
    "compose_answer",
    "execute_sql",
    "generate_sql",
    "honest_refusal",
    "load_schema",
    "sanity_check",
    "validate_sql",
]

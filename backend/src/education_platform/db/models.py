"""Import all ORM modules so Alembic and metadata consumers see every table."""

from education_platform.modules.academics import models as academics_models
from education_platform.modules.assessments import models as assessments_models
from education_platform.modules.assistant import models as assistant_models
from education_platform.modules.at_risk import models as at_risk_models
from education_platform.modules.attendance import models as attendance_models
from education_platform.modules.audit import models as audit_models
from education_platform.modules.auth import models as auth_models
from education_platform.modules.materials import models as materials_models
from education_platform.modules.rag import models as rag_models

__all__ = [
    "academics_models",
    "assessments_models",
    "assistant_models",
    "at_risk_models",
    "attendance_models",
    "audit_models",
    "auth_models",
    "materials_models",
    "rag_models",
]

"""Module-shape conventions that the backend refactor holds to."""

from __future__ import annotations

import inspect

import education_platform.modules.assessments.service as assessments_service
import education_platform.modules.materials as materials
import education_platform.modules.materials.service as materials_service
from education_platform.db import models as _models
from education_platform.db.base import Base
from education_platform.modules.academics.constants import POC_INSTITUTION_NAME
from education_platform.modules.assessments.queries import (
    open_release_for_quiz_version,
    questions_for_quiz_version,
    released_quiz,
)

_ = _models


def test_at_risk_flags_are_registered_on_metadata() -> None:
    assert "at_risk_flags" in Base.metadata.tables


def test_materials_package_does_not_export_router() -> None:
    assert "router" not in getattr(materials, "__all__", ())
    assert "router" not in inspect.getsource(materials)


def test_poc_constants_live_in_academics() -> None:
    assert POC_INSTITUTION_NAME == "POC Demo School"


def test_assessments_does_not_import_materials_service() -> None:
    assert "materials.service" not in inspect.getsource(assessments_service)


def test_materials_does_not_import_assessments_service() -> None:
    assert "assessments.service" not in inspect.getsource(materials_service)


def test_quiz_helpers_live_in_assessments_queries() -> None:
    assert open_release_for_quiz_version.__module__.endswith("assessments.queries")
    assert questions_for_quiz_version.__module__.endswith("assessments.queries")
    assert released_quiz.__module__.endswith("assessments.queries")


def test_learning_directory_lives_in_academics() -> None:
    from education_platform.modules.academics.directory import build_learning_directory

    assert build_learning_directory.__module__.endswith("academics.directory")


def test_audit_events_are_registered_on_metadata() -> None:
    assert "audit_events" in Base.metadata.tables


def test_student_360_register_is_shared() -> None:
    import education_platform.modules.at_risk.service as at_risk_service
    import education_platform.modules.insights.service as insights_service

    assert "FINISHED_ATTEMPT_STATUSES" in inspect.getsource(insights_service)
    assert "FINISHED_ATTEMPT_STATUSES" in inspect.getsource(at_risk_service)
    assert "STUDENT_360_SIGNAL_COLUMNS" in inspect.getsource(at_risk_service)


def test_seed_helpers_are_split() -> None:
    from education_platform.modules.materials.seed_content import upsert_material_version
    from education_platform.modules.materials.seed_curriculum import ensure_curriculum_root
    from education_platform.modules.materials.seed_quizzes import upsert_subtopic_quiz

    assert ensure_curriculum_root.__module__.endswith("materials.seed_curriculum")
    assert upsert_material_version.__module__.endswith("materials.seed_content")
    assert upsert_subtopic_quiz.__module__.endswith("materials.seed_quizzes")

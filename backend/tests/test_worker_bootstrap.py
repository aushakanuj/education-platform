"""Worker process must register all ORM tables before flushing ingest rows."""

from __future__ import annotations

import subprocess
import sys


def test_worker_process_resolves_source_version_user_fk() -> None:
    """A fresh interpreter (no FastAPI app import) must resolve SMV → users.

    ``python -m education_platform.workers`` does not load ``main.app``. Without
    importing the auth models, flushing source chunks raises
    ``NoReferencedTableError`` on ``source_material_versions.submitted_by_user_id``.
    """
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "from education_platform.workers.runner import poll_once\n"
            "from education_platform.modules.materials.models import SourceMaterialVersion\n"
            "from education_platform.modules.generation.models import ContentGenerationRun\n"
            "SourceMaterialVersion.__mapper__._sorted_tables\n"
            "ContentGenerationRun.__mapper__._sorted_tables\n"
            "assert poll_once is not None\n",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

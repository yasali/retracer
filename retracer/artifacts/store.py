"""Artifact storage — organize and index run outputs."""

from __future__ import annotations

import logging
from pathlib import Path

from retracer.models.artifact_ref import ArtifactRef
from retracer.models.run_result import RunResult
from retracer.utils.fs import write_json

logger = logging.getLogger(__name__)


def build_artifact_index(run: RunResult, output_dir: Path) -> Path:
    """Create an artifact index JSON for a run, listing all captured files."""
    artifacts: list[dict] = []

    for ref in run.screenshots:
        artifacts.append({
            "kind": ref.kind.value,
            "path": str(ref.path),
            "label": ref.label,
            "step": ref.step,
        })

    for ref in run.logs:
        artifacts.append({
            "kind": ref.kind.value,
            "path": str(ref.path),
            "label": ref.label,
        })

    index = {
        "run_id": run.run_id,
        "incident_id": run.incident_id,
        "adapter": run.adapter,
        "flow_id": run.flow_id,
        "status": run.status.value,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
    }

    index_path = output_dir / "artifact_index.json"
    write_json(index_path, index)
    logger.info("Artifact index: %s (%d items)", index_path, len(artifacts))
    return index_path

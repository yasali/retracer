"""Incident submission — validate inputs and persist an incident manifest."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from retracer.models.incident import Incident, IncidentStatus, Platform
from retracer.security import validate_path_exists
from retracer.utils.fs import ensure_dir, read_json, write_json
from retracer.utils.timestamps import utc_now

logger = logging.getLogger(__name__)


def _next_incident_id(output_dir: Path) -> str:
    """Generate the next sequential incident ID."""
    existing = sorted(output_dir.glob("inc_*")) if output_dir.exists() else []
    num = len(existing) + 1
    return f"inc_{num:04d}"


def submit_incident(
    *,
    platform: str,
    description: str,
    output_dir: Path,
    image_path: str | None = None,
    fixture: str | None = None,
    bundle_id: str | None = None,
    app_path: str | None = None,
    notes: str | None = None,
) -> Incident:
    """Validate inputs, create incident manifest, persist to disk."""
    # Validate platform
    try:
        plat = Platform(platform.lower())
    except ValueError:
        valid = ", ".join(p.value for p in Platform)
        raise ValueError(f"Invalid platform: {platform!r}. Must be one of: {valid}")

    # Validate image path if provided
    resolved_image = None
    if image_path:
        resolved_image = validate_path_exists(Path(image_path), label="Bug screenshot")

    # Validate app path if provided
    resolved_app = None
    if app_path:
        resolved_app = validate_path_exists(Path(app_path), label="App bundle")

    # Validate bundle ID format
    if bundle_id:
        from retracer.security import validate_bundle_id
        validate_bundle_id(bundle_id)

    incident_id = _next_incident_id(output_dir)
    incident_dir = ensure_dir(output_dir / incident_id)

    # Copy reference image into incident dir if provided
    stored_image = None
    if resolved_image:
        stored_image = incident_dir / f"reference{resolved_image.suffix}"
        shutil.copy2(resolved_image, stored_image)
        logger.info("Copied reference image to %s", stored_image)

    incident = Incident(
        incident_id=incident_id,
        platform=plat,
        description=description,
        image_path=stored_image,
        fixture=fixture,
        bundle_id=bundle_id,
        app_path=resolved_app,
        notes=notes,
        status=IncidentStatus.SUBMITTED,
        created_at=utc_now(),
    )

    # Persist manifest
    manifest_path = incident_dir / "manifest.json"
    write_json(manifest_path, incident.model_dump(mode="json"))
    logger.info("Created incident %s at %s", incident_id, incident_dir)

    return incident


def load_incident(incident_id: str, output_dir: Path) -> Incident:
    """Load an existing incident from its manifest."""
    manifest_path = output_dir / incident_id / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Incident not found: {incident_id} (looked at {manifest_path})")
    data = read_json(manifest_path)
    return Incident.model_validate(data)

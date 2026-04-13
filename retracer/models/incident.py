"""Canonical incident model — the entry point for every bug reproduction."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


class Platform(str, Enum):
    IOS = "ios"
    TVOS = "tvos"
    ANDROID = "android"
    WEB = "web"


class IncidentStatus(str, Enum):
    SUBMITTED = "submitted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Incident(BaseModel):
    """Immutable snapshot of a submitted bug report."""

    incident_id: str
    platform: Platform
    description: str
    image_path: Path | None = None
    fixture: str | None = None
    bundle_id: str | None = None
    app_path: Path | None = None
    notes: str | None = None
    status: IncidentStatus = IncidentStatus.SUBMITTED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = Field(default_factory=dict)

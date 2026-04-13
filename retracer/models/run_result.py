"""Canonical run result — every automation adapter must produce this exact shape."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from retracer.models.artifact_ref import ArtifactRef


class RunStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    TIMEOUT = "timeout"


class RunResult(BaseModel):
    """Output of a single flow execution by any automation adapter.

    This is the canonical contract between runners and downstream stages
    (scoring, reporting). Adapters must produce this shape regardless of
    whether they use Maestro, XCUITest, Appium, or Playwright.
    """

    run_id: str
    incident_id: str
    adapter: str  # "maestro", "xcuitest", "appium", "playwright"
    platform: str
    flow_id: str
    status: RunStatus
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    exit_code: int = -1
    screenshots: list[ArtifactRef] = Field(default_factory=list)
    logs: list[ArtifactRef] = Field(default_factory=list)
    ui_tree: dict | None = None
    metadata: dict = Field(default_factory=dict)

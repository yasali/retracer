"""Canonical artifact reference — uniform way to point at any output file."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel


class ArtifactKind(str, Enum):
    SCREENSHOT = "screenshot"
    LOG = "log"
    UI_TREE = "ui_tree"
    VIDEO = "video"
    REPORT = "report"
    BUNDLE = "bundle"
    OTHER = "other"


class ArtifactRef(BaseModel):
    """Pointer to a stored artifact. Every module produces and consumes these."""

    path: Path
    kind: ArtifactKind
    label: str = ""
    step: str | None = None  # Which pipeline stage / flow step produced this
    metadata: dict = {}

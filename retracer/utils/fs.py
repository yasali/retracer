"""Filesystem utilities — safe path operations."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def ensure_dir(path: Path) -> Path:
    """Create a directory (and parents) if it doesn't exist."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, data: dict) -> Path:
    """Write a dict as pretty-printed JSON."""
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, default=str) + "\n")
    logger.debug("Wrote %s", path)
    return path


def read_json(path: Path) -> dict:
    """Read JSON from a file."""
    return json.loads(path.read_text())

"""Timestamp utilities."""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_stamp() -> str:
    return utc_now().isoformat()


def file_stamp() -> str:
    """Filesystem-safe timestamp string."""
    return utc_now().strftime("%Y%m%d_%H%M%S")

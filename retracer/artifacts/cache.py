"""Content-addressable cache — SHA256-keyed results.

Inspired by Graphify's caching pattern and Git's content-addressable storage.
If the inputs haven't changed, the output is reused. This is critical for
CI where runs are frequent and redundant work is expensive.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def content_hash(*parts: str) -> str:
    """Compute a SHA256 hash from one or more string parts."""
    hasher = hashlib.sha256()
    for part in parts:
        hasher.update(part.encode())
        hasher.update(b"\0")  # separator
    return hasher.hexdigest()


def file_hash(path: Path) -> str:
    """Compute SHA256 of a file's contents."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


class ResultCache:
    """Cache for flow run results, keyed by content hash."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _key_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def get(self, key: str) -> dict | None:
        """Retrieve a cached result by key, or None if not cached."""
        path = self._key_path(key)
        if path.exists():
            logger.debug("Cache hit: %s", key[:12])
            return json.loads(path.read_text())
        return None

    def put(self, key: str, data: dict) -> None:
        """Store a result in the cache."""
        path = self._key_path(key)
        path.write_text(json.dumps(data, indent=2, default=str) + "\n")
        logger.debug("Cache write: %s", key[:12])

    def make_key(self, flow_id: str, flow_path: Path, fixture: str | None = None) -> str:
        """Build a cache key from flow file content + fixture."""
        parts = [flow_id, file_hash(flow_path)]
        if fixture:
            parts.append(fixture)
        return content_hash(*parts)

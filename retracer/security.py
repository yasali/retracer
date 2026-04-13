"""Security boundary — all external input validation in one place.

Every module that touches file paths, shell commands, or credentials
must go through this module. This is the single point of enforcement
(inspired by Graphify's security.py pattern).
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

# Characters allowed in shell arguments (conservative allowlist)
_SAFE_SHELL_CHARS = re.compile(r"^[a-zA-Z0-9_./:@=, -]+$")

# Fields that must never appear in logs or reports
SECRET_FIELDS: frozenset[str] = frozenset({
    "password", "secret", "token", "api_key", "private_key",
    "credentials", "auth_token", "access_token",
})


def validate_path(path: Path, allowed_root: Path) -> Path:
    """Ensure a path resolves inside the allowed root directory.

    Prevents directory traversal attacks (e.g. ../../etc/passwd).
    Raises ValueError if the resolved path escapes the root.
    """
    resolved = path.resolve()
    root_resolved = allowed_root.resolve()
    if not str(resolved).startswith(str(root_resolved)):
        raise ValueError(
            f"Path escapes allowed root: {path} resolves to {resolved}, "
            f"which is outside {root_resolved}"
        )
    return resolved


def validate_path_exists(path: Path, label: str = "File") -> Path:
    """Check that a path exists and return it resolved."""
    resolved = path.resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"{label} not found: {resolved}")
    return resolved


def sanitize_shell_arg(arg: str) -> str:
    """Validate a string is safe for shell argument use.

    Uses an allowlist approach — if the argument contains characters
    outside the safe set, it is shell-quoted. This prevents injection
    even if callers forget to quote.
    """
    if _SAFE_SHELL_CHARS.match(arg):
        return arg
    return shlex.quote(arg)


def redact_secrets(data: dict, extra_fields: frozenset[str] | None = None) -> dict:
    """Return a copy of data with secret field values replaced by [REDACTED].

    Recurses into nested dicts. Does not mutate the original.
    """
    fields = SECRET_FIELDS | (extra_fields or frozenset())
    result = {}
    for key, value in data.items():
        if key.lower() in fields:
            result[key] = "[REDACTED]"
        elif isinstance(value, dict):
            result[key] = redact_secrets(value, extra_fields)
        else:
            result[key] = value
    return result


def validate_bundle_id(bundle_id: str) -> str:
    """Validate an app bundle identifier format (reverse DNS)."""
    pattern = re.compile(r"^[a-zA-Z][a-zA-Z0-9-]*(\.[a-zA-Z][a-zA-Z0-9-]*)+$")
    if not pattern.match(bundle_id):
        raise ValueError(
            f"Invalid bundle ID format: {bundle_id!r}. "
            "Expected reverse DNS format like com.example.app"
        )
    return bundle_id

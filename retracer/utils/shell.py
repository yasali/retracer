"""Shell execution utilities — safe subprocess wrappers."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from retracer.security import sanitize_shell_arg

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 120  # seconds

# Extra bin directories to search for tools (e.g. Maestro installs to ~/.maestro/bin)
_EXTRA_PATH_DIRS: list[str] = [
    str(Path.home() / ".maestro" / "bin"),
]


@dataclass
class ShellResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


def _resolve_command(cmd: str) -> str:
    """Find the full path to a command, checking extra directories if needed."""
    found = shutil.which(cmd)
    if found:
        return found
    for extra_dir in _EXTRA_PATH_DIRS:
        candidate = os.path.join(extra_dir, cmd)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return cmd  # fall through — let subprocess raise FileNotFoundError


def _env_with_extra_path(env: dict[str, str] | None) -> dict[str, str]:
    """Return an env dict with extra bin dirs prepended to PATH."""
    base = env if env is not None else dict(os.environ)
    extra = os.pathsep.join(_EXTRA_PATH_DIRS)
    base["PATH"] = extra + os.pathsep + base.get("PATH", "")
    return base


def run_cmd(
    cmd: list[str],
    *,
    timeout: int = DEFAULT_TIMEOUT,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> ShellResult:
    """Run a command safely with timeout and logging.

    All arguments are validated through the security module.
    Automatically searches ~/.maestro/bin and other extra directories.
    """
    resolved_cmd = [_resolve_command(cmd[0])] + cmd[1:]
    sanitized = [sanitize_shell_arg(arg) for arg in resolved_cmd]
    logger.debug("Running: %s", " ".join(sanitized))

    run_env = _env_with_extra_path(env)

    try:
        proc = subprocess.run(
            resolved_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=run_env,
        )
        return ShellResult(
            command=cmd,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Command timed out after %ds: %s", timeout, " ".join(sanitized))
        return ShellResult(command=cmd, returncode=-1, stdout="", stderr="timeout")
    except FileNotFoundError:
        logger.error("Command not found: %s", cmd[0])
        return ShellResult(command=cmd, returncode=-1, stdout="", stderr=f"not found: {cmd[0]}")


def check_tool_available(tool: str) -> bool:
    """Check if a CLI tool is available on PATH."""
    result = run_cmd(["which", tool], timeout=5)
    return result.returncode == 0

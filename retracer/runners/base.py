"""Runner adapter base — protocol that all automation backends must implement.

The pipeline never knows whether Maestro, XCUITest, Appium, or Playwright
is running the flows. Every adapter produces the canonical RunResult.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from retracer.config import Config
from retracer.models.incident import Incident
from retracer.models.run_result import RunResult

# Registry of available runners
_RUNNERS: dict[str, "AutomationAdapter"] = {}


class AutomationAdapter(Protocol):
    """Interface that every automation backend must implement."""

    @property
    def name(self) -> str:
        """Short identifier for this adapter (e.g. 'maestro', 'xcuitest')."""
        ...

    def run_flow(
        self,
        *,
        flow_id: str,
        run_id: str,
        incident: Incident,
        output_dir: Path,
        config: Config,
    ) -> RunResult:
        """Execute a single flow and return a canonical RunResult."""
        ...


def register_runner(runner: AutomationAdapter) -> AutomationAdapter:
    """Register an automation adapter in the global registry."""
    _RUNNERS[runner.name] = runner
    return runner


def get_runner(name: str) -> AutomationAdapter:
    """Look up a registered runner by name."""
    # Ensure platform modules are imported so runners register themselves
    _ensure_runners_loaded()
    if name not in _RUNNERS:
        available = ", ".join(_RUNNERS.keys()) or "(none)"
        raise ValueError(f"Unknown runner: {name!r}. Available: {available}")
    return _RUNNERS[name]


def _ensure_runners_loaded() -> None:
    """Import runner modules to trigger registration."""
    if _RUNNERS:
        return
    try:
        import retracer.runners.maestro_runner  # noqa: F401
    except ImportError:
        pass
    try:
        import retracer.runners.simctl_runner  # noqa: F401
    except ImportError:
        pass

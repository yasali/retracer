"""Global configuration — resolved from CLI args, env vars, and defaults."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    """Top-level configuration for a retracer session."""

    project_root: Path = field(default_factory=lambda: Path.cwd())
    output_dir: Path = field(default_factory=lambda: Path("runs"))
    flows_dir: Path = field(default_factory=lambda: Path("flows"))
    fixtures_dir: Path = field(default_factory=lambda: Path("fixtures"))

    # Automation
    default_adapter: str = "maestro"
    run_timeout: int = 300  # seconds per flow

    # Scoring
    scoring_method: str = "structural"

    # Planning
    planner_type: str = "rule"  # "rule" or "llm"

    # Feature flags for graceful degradation
    scoring_enabled: bool = True
    preflight_enabled: bool = True

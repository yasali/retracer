"""Pipeline context — the single data object that flows through every stage."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from retracer.models.incident import Incident
from retracer.models.run_result import RunResult
from retracer.models.score_result import ScoreResult


@dataclass
class PreflightResult:
    """Output of environment validation."""

    passed: bool
    checks: dict[str, bool] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)


@dataclass
class PlanResult:
    """Output of the scenario planner."""

    flow_ids: list[str] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)
    planner_name: str = "unknown"


@dataclass
class ReportResult:
    """Output of the report generator."""

    report_path: Path | None = None
    bundle_path: Path | None = None


@dataclass
class PipelineContext:
    """Canonical data object that flows through every pipeline stage.

    Each stage reads from this context and writes its results back into it.
    Stages must not mutate fields they don't own — they return a new or
    updated context. This is the single contract that holds the system together.
    """

    incident: Incident
    output_dir: Path = field(default_factory=lambda: Path("runs"))

    # Populated by pipeline stages
    preflight: PreflightResult | None = None
    plan: PlanResult | None = None
    runs: list[RunResult] = field(default_factory=list)
    scores: list[ScoreResult] = field(default_factory=list)
    report: ReportResult | None = None

    @property
    def incident_dir(self) -> Path:
        return self.output_dir / self.incident.incident_id

    @property
    def next_run_id(self) -> str:
        return f"run_{len(self.runs) + 1:03d}"

    @property
    def best_score(self) -> ScoreResult | None:
        if not self.scores:
            return None
        return max(self.scores, key=lambda s: s.score)

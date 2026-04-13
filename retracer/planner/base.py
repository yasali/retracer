"""Planner protocol and registry.

The planner selects candidate reproduction flows from the incident description.
Multiple implementations can coexist (rule-based, LLM-based, image-aware).
The pipeline calls the planner through this interface — it never knows which
implementation is active.
"""

from __future__ import annotations

from typing import Protocol

from retracer.models.pipeline_context import PlanResult

_PLANNERS: dict[str, "PlannerAdapter"] = {}


class PlannerAdapter(Protocol):
    """Interface for flow selection strategies."""

    @property
    def name(self) -> str: ...

    def plan(
        self,
        *,
        description: str,
        platform: str,
        fixture: str | None = None,
        image_path: str | None = None,
    ) -> PlanResult: ...


def register_planner(planner: PlannerAdapter) -> PlannerAdapter:
    _PLANNERS[planner.name] = planner
    return planner


def get_planner(name: str) -> PlannerAdapter:
    _ensure_planners_loaded()
    if name not in _PLANNERS:
        available = ", ".join(_PLANNERS.keys()) or "(none)"
        raise ValueError(f"Unknown planner: {name!r}. Available: {available}")
    return _PLANNERS[name]


def _ensure_planners_loaded() -> None:
    if _PLANNERS:
        return
    try:
        import retracer.planner.rule_planner  # noqa: F401
    except ImportError:
        pass

"""Scoring adapter base — protocol and registry for screenshot comparison.

Every scorer produces the canonical ScoreResult with confidence labels
(CONFIRMED, LIKELY, POSSIBLE, INCONCLUSIVE). Multiple scorers can be
composed or swapped without changing the pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from retracer.models.artifact_ref import ArtifactRef
from retracer.models.score_result import ScoreResult

_SCORERS: dict[str, "ScoringAdapter"] = {}


class ScoringAdapter(Protocol):
    @property
    def name(self) -> str: ...

    def score(
        self,
        *,
        reference: Path,
        candidates: list[ArtifactRef],
        run_id: str,
    ) -> ScoreResult: ...


def register_scorer(scorer: ScoringAdapter) -> ScoringAdapter:
    _SCORERS[scorer.name] = scorer
    return scorer


def get_scorer(name: str) -> ScoringAdapter:
    _ensure_scorers_loaded()
    if name not in _SCORERS:
        available = ", ".join(_SCORERS.keys()) or "(none)"
        raise ValueError(f"Unknown scorer: {name!r}. Available: {available}")
    return _SCORERS[name]


def _ensure_scorers_loaded() -> None:
    if _SCORERS:
        return
    try:
        import retracer.scoring.structural_scorer  # noqa: F401
    except ImportError:
        pass

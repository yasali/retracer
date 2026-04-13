"""Canonical score result — every scoring adapter must produce this shape."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from retracer.models.artifact_ref import ArtifactRef


class Confidence(str, Enum):
    """Graduated confidence labels inspired by Graphify's provenance system.

    CONFIRMED — Visual match + same UI state + same error
    LIKELY    — Screenshots are structurally similar, flow reached the right screen
    POSSIBLE  — Flow ran without error but evidence is weak
    INCONCLUSIVE — Flow failed or evidence doesn't match
    """

    CONFIRMED = "CONFIRMED"
    LIKELY = "LIKELY"
    POSSIBLE = "POSSIBLE"
    INCONCLUSIVE = "INCONCLUSIVE"


class ScoreResult(BaseModel):
    """Output of comparing a reference screenshot against run captures.

    Produced by any ScoringAdapter. The confidence label is machine-actionable:
    downstream stages can filter, sort, or gate on it.
    """

    run_id: str
    best_match: ArtifactRef | None = None
    confidence: Confidence = Confidence.INCONCLUSIVE
    score: float = 0.0  # 0.0 – 1.0 normalized
    method: str = "none"  # "structural", "pixel", "ocr", "ml"
    evidence: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

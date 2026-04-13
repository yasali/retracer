"""Structural scorer — MVP heuristic comparison with zero optional dependencies.

Compares reference and candidate screenshots using file metadata only:
- File existence
- Image dimensions (if Pillow is available — graceful degradation)
- File size ratio

This is intentionally simple. The interface is identical to future
PixelScorer, OCRScorer, and MLScorer — swap via config, not code changes.
"""

from __future__ import annotations

import logging
from pathlib import Path

from retracer.models.artifact_ref import ArtifactRef
from retracer.models.score_result import Confidence, ScoreResult
from retracer.scoring.base import register_scorer

logger = logging.getLogger(__name__)


class StructuralScorer:
    @property
    def name(self) -> str:
        return "structural"

    def score(
        self,
        *,
        reference: Path,
        candidates: list[ArtifactRef],
        run_id: str,
    ) -> ScoreResult:
        if not reference.exists():
            return ScoreResult(
                run_id=run_id,
                confidence=Confidence.INCONCLUSIVE,
                evidence=["Reference image not found"],
            )

        if not candidates:
            return ScoreResult(
                run_id=run_id,
                confidence=Confidence.INCONCLUSIVE,
                evidence=["No candidate screenshots to compare"],
            )

        ref_size = reference.stat().st_size
        best_score = 0.0
        best_match: ArtifactRef | None = None
        evidence: list[str] = []

        for candidate in candidates:
            if not candidate.path.exists():
                continue

            score = 0.0
            reasons: list[str] = []

            # File size similarity (quick heuristic)
            cand_size = candidate.path.stat().st_size
            if ref_size > 0 and cand_size > 0:
                ratio = min(ref_size, cand_size) / max(ref_size, cand_size)
                score += ratio * 0.3
                reasons.append(f"size ratio: {ratio:.2f}")

            # Dimension comparison (if Pillow available — graceful degradation)
            dim_score = self._compare_dimensions(reference, candidate.path)
            if dim_score is not None:
                score += dim_score * 0.7
                reasons.append(f"dimension similarity: {dim_score:.2f}")
            else:
                # Without Pillow, size ratio gets full weight
                score += ratio * 0.4 if ref_size > 0 else 0.0
                reasons.append("Pillow not available, using size heuristic only")

            if score > best_score:
                best_score = score
                best_match = candidate
                evidence = reasons

        confidence = self._score_to_confidence(best_score)

        return ScoreResult(
            run_id=run_id,
            best_match=best_match,
            confidence=confidence,
            score=round(best_score, 3),
            method=self.name,
            evidence=evidence,
        )

    def _compare_dimensions(self, ref: Path, candidate: Path) -> float | None:
        """Compare image dimensions. Returns similarity 0-1, or None if Pillow missing."""
        try:
            from PIL import Image
        except ImportError:
            return None

        try:
            with Image.open(ref) as ref_img, Image.open(candidate) as cand_img:
                rw, rh = ref_img.size
                cw, ch = cand_img.size
                width_sim = min(rw, cw) / max(rw, cw) if max(rw, cw) > 0 else 0
                height_sim = min(rh, ch) / max(rh, ch) if max(rh, ch) > 0 else 0
                return (width_sim + height_sim) / 2
        except Exception as e:
            logger.debug("Dimension comparison failed: %s", e)
            return None

    def _score_to_confidence(self, score: float) -> Confidence:
        if score >= 0.85:
            return Confidence.CONFIRMED
        if score >= 0.6:
            return Confidence.LIKELY
        if score >= 0.3:
            return Confidence.POSSIBLE
        return Confidence.INCONCLUSIVE


register_scorer(StructuralScorer())

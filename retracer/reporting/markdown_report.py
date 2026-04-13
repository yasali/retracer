"""Markdown report generator — structured, human-readable bug reports."""

from __future__ import annotations

import logging
from pathlib import Path

from retracer.config import Config
from retracer.models.pipeline_context import PipelineContext, ReportResult
from retracer.models.run_result import RunStatus
from retracer.models.score_result import Confidence
from retracer.utils.fs import ensure_dir, write_json

logger = logging.getLogger(__name__)


def generate_report(ctx: PipelineContext, config: Config) -> ReportResult:
    """Generate a markdown report and bundle JSON from pipeline results."""
    incident_dir = ensure_dir(ctx.incident_dir)
    report_path = incident_dir / "report.md"
    bundle_path = incident_dir / "bundle.json"

    lines: list[str] = []
    _section = lines.append

    # Header
    _section(f"# Bug Report: {ctx.incident.incident_id}\n")
    _section(f"**Platform:** {ctx.incident.platform.value}")
    _section(f"**Created:** {ctx.incident.created_at.isoformat()}")
    _section(f"**Status:** {ctx.incident.status.value}\n")

    # Incident description
    _section("## Description\n")
    _section(ctx.incident.description + "\n")

    if ctx.incident.fixture:
        _section(f"**Fixture:** {ctx.incident.fixture}\n")

    if ctx.incident.image_path:
        _section(f"**Reference image:** `{ctx.incident.image_path}`\n")

    # Preflight
    if ctx.preflight:
        _section("## Preflight Checks\n")
        status = "PASSED" if ctx.preflight.passed else "FAILED"
        _section(f"**Result:** {status}\n")
        for name, ok in ctx.preflight.checks.items():
            icon = "✅" if ok else "❌"
            _section(f"- {icon} {name}")
        if ctx.preflight.messages:
            _section("")
            for msg in ctx.preflight.messages:
                _section(f"> {msg}")
        _section("")

    # Planning
    if ctx.plan:
        _section("## Planner Decision\n")
        _section(f"**Planner:** {ctx.plan.planner_name}")
        _section(f"**Flows selected:** {len(ctx.plan.flow_ids)}\n")
        for reason in ctx.plan.reasoning:
            _section(f"- {reason}")
        _section("")

    # Run results
    if ctx.runs:
        _section("## Flows Attempted\n")
        _section("| Run | Flow | Status | Exit | Screenshots | Duration |")
        _section("|-----|------|--------|------|-------------|----------|")
        for run in ctx.runs:
            duration = ""
            if run.finished_at and run.started_at:
                delta = run.finished_at - run.started_at
                duration = f"{delta.total_seconds():.1f}s"
            _section(
                f"| {run.run_id} | {run.flow_id} | {run.status.value} | "
                f"{run.exit_code} | {len(run.screenshots)} | {duration} |"
            )
        _section("")

        # Screenshots
        all_screenshots = [s for r in ctx.runs for s in r.screenshots]
        if all_screenshots:
            _section("### Captured Screenshots\n")
            for ss in all_screenshots:
                _section(f"- `{ss.path}` ({ss.label})")
            _section("")

    # Scoring
    if ctx.scores:
        _section("## Scoring Results\n")
        _section("| Run | Confidence | Score | Method | Best Match |")
        _section("|-----|-----------|-------|--------|------------|")
        for score in ctx.scores:
            match_path = str(score.best_match.path) if score.best_match else "—"
            _section(
                f"| {score.run_id} | **{score.confidence.value}** | "
                f"{score.score:.3f} | {score.method} | `{match_path}` |"
            )
        _section("")

        # Evidence
        for score in ctx.scores:
            if score.evidence:
                _section(f"**{score.run_id} evidence:**")
                for ev in score.evidence:
                    _section(f"- {ev}")
                _section("")

    # Summary
    best = ctx.best_score
    _section("## Summary\n")
    if best and best.confidence in (Confidence.CONFIRMED, Confidence.LIKELY):
        _section(f"**Bug likely reproduced** (confidence: {best.confidence.value}, score: {best.score:.3f})")
        _section(f"Best matching run: {best.run_id}")
    elif best and best.confidence == Confidence.POSSIBLE:
        _section(f"**Possible reproduction** (confidence: {best.confidence.value}, score: {best.score:.3f})")
        _section("Manual review recommended.")
    else:
        passed_runs = [r for r in ctx.runs if r.status == RunStatus.PASSED]
        _section(f"**Reproduction inconclusive.** {len(passed_runs)}/{len(ctx.runs)} flows passed.")
        _section("Consider providing a reference screenshot or adjusting flows.")

    _section("")

    # Next steps
    _section("## Suggested Next Steps\n")
    if not ctx.incident.image_path:
        _section("- Provide a reference screenshot for similarity scoring")
    if not ctx.scores or all(s.confidence == Confidence.INCONCLUSIVE for s in ctx.scores):
        _section("- Try additional flows or manual reproduction")
        _section("- Check if the bug requires specific account/fixture state")
    if any(r.status == RunStatus.ERROR for r in ctx.runs):
        _section("- Investigate flow errors — check logs for details")
    _section("- Review captured screenshots for visual confirmation")
    _section("")

    # Write report
    report_path.write_text("\n".join(lines))
    logger.info("Report written to %s", report_path)

    # Write bundle JSON
    bundle = {
        "incident_id": ctx.incident.incident_id,
        "manifest_path": str(ctx.incident_dir / "manifest.json"),
        "run_ids": [r.run_id for r in ctx.runs],
        "latest_status": ctx.incident.status.value,
        "best_score": {
            "run_id": best.run_id,
            "confidence": best.confidence.value,
            "score": best.score,
        } if best else None,
        "report_path": str(report_path),
    }
    write_json(bundle_path, bundle)

    return ReportResult(report_path=report_path, bundle_path=bundle_path)

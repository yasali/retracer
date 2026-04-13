"""Pipeline engine — explicit linear chain of pure stages.

Inspired by Graphify's pipeline architecture (Unix philosophy):
each stage does one thing, takes PipelineContext in, returns PipelineContext out.
No shared mutable state between stages. Any stage can be swapped or skipped.

Pipeline:
  intake → preflight → plan → execute → capture → score → report
"""

from __future__ import annotations

import logging
from typing import Callable

from retracer.config import Config
from retracer.models.pipeline_context import PipelineContext

logger = logging.getLogger(__name__)

# Type alias for a pipeline stage function
Stage = Callable[[PipelineContext, Config], PipelineContext]


def preflight_stage(ctx: PipelineContext, config: Config) -> PipelineContext:
    """Validate the environment before running flows."""
    if not config.preflight_enabled:
        logger.info("Preflight disabled, skipping")
        return ctx

    from retracer.environment.preflight import run_preflight

    ctx.preflight = run_preflight(ctx.incident, config)

    if not ctx.preflight.passed:
        for msg in ctx.preflight.messages:
            logger.warning("Preflight: %s", msg)

    return ctx


def planning_stage(ctx: PipelineContext, config: Config) -> PipelineContext:
    """Select candidate reproduction flows."""
    from retracer.planner.base import get_planner

    planner = get_planner(config.planner_type)
    ctx.plan = planner.plan(
        description=ctx.incident.description,
        platform=ctx.incident.platform.value,
        fixture=ctx.incident.fixture,
        image_path=str(ctx.incident.image_path) if ctx.incident.image_path else None,
    )
    logger.info(
        "Planner (%s) selected %d flows: %s",
        ctx.plan.planner_name,
        len(ctx.plan.flow_ids),
        ctx.plan.flow_ids,
    )
    return ctx


def execution_stage(ctx: PipelineContext, config: Config) -> PipelineContext:
    """Run candidate flows through the automation adapter."""
    from retracer.runners.base import get_runner

    if not ctx.plan or not ctx.plan.flow_ids:
        logger.warning("No flows to execute")
        return ctx

    runner = get_runner(config.default_adapter)

    for flow_id in ctx.plan.flow_ids:
        run_id = ctx.next_run_id
        logger.info("Executing flow %s as %s", flow_id, run_id)

        try:
            result = runner.run_flow(
                flow_id=flow_id,
                run_id=run_id,
                incident=ctx.incident,
                output_dir=ctx.incident_dir / run_id,
                config=config,
            )
            ctx.runs.append(result)
        except FileNotFoundError as e:
            logger.warning("Skipping flow %s: %s", flow_id, e)
        except Exception as e:
            logger.error("Flow %s failed unexpectedly: %s", flow_id, e)

    return ctx


def scoring_stage(ctx: PipelineContext, config: Config) -> PipelineContext:
    """Score run screenshots against reference image."""
    if not config.scoring_enabled:
        logger.info("Scoring disabled, skipping")
        return ctx

    if not ctx.incident.image_path:
        logger.info("No reference image provided, skipping scoring")
        return ctx

    from retracer.scoring.base import get_scorer

    scorer = get_scorer(config.scoring_method)

    for run in ctx.runs:
        if not run.screenshots:
            continue
        score = scorer.score(
            reference=ctx.incident.image_path,
            candidates=run.screenshots,
            run_id=run.run_id,
        )
        ctx.scores.append(score)

    return ctx


def reporting_stage(ctx: PipelineContext, config: Config) -> PipelineContext:
    """Generate the final markdown report and bundle."""
    from retracer.reporting.markdown_report import generate_report

    ctx.report = generate_report(ctx, config)
    return ctx


# Default pipeline: all stages in order
DEFAULT_STAGES: list[Stage] = [
    preflight_stage,
    planning_stage,
    execution_stage,
    scoring_stage,
    reporting_stage,
]


def execute_pipeline(
    ctx: PipelineContext,
    config: Config,
    stages: list[Stage] | None = None,
) -> PipelineContext:
    """Run the full pipeline or a custom subset of stages.

    Each stage is a pure function: (PipelineContext, Config) → PipelineContext.
    Failures in one stage log a warning but don't block subsequent stages
    unless the stage explicitly raises.
    """
    stages = stages or DEFAULT_STAGES
    logger.info("Starting pipeline with %d stages for %s", len(stages), ctx.incident.incident_id)

    for stage in stages:
        stage_name = stage.__name__
        logger.info("→ %s", stage_name)
        try:
            ctx = stage(ctx, config)
        except Exception:
            logger.exception("Stage %s failed", stage_name)
            raise

    logger.info("Pipeline complete for %s", ctx.incident.incident_id)
    return ctx

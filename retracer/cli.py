"""CLI entry point — Click-based command interface."""

from __future__ import annotations

import logging
import sys

import click
from rich.console import Console
from rich.table import Table

console = Console()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
def main(verbose: bool) -> None:
    """Bug Agent — UI bug reproduction and triage tool."""
    _setup_logging(verbose)
    # Ensure platform configs are loaded
    import retracer.platforms.ios  # noqa: F401
    import retracer.platforms.tvos  # noqa: F401


@main.command()
@click.option("--platform", "-p", required=True, help="Target platform (ios, tvos)")
@click.option("--description", "-d", required=True, help="Bug description")
@click.option("--image", "-i", default=None, help="Path to reference screenshot")
@click.option("--fixture", "-f", default=None, help="Fixture name")
@click.option("--bundle-id", default=None, help="App bundle ID")
@click.option("--app-path", default=None, help="Path to .app bundle")
@click.option("--output-dir", default="runs", help="Output directory")
def submit(
    platform: str,
    description: str,
    image: str | None,
    fixture: str | None,
    bundle_id: str | None,
    app_path: str | None,
    output_dir: str,
) -> None:
    """Submit a new bug for reproduction."""
    from pathlib import Path

    from retracer.intake.submit import submit_incident

    try:
        incident = submit_incident(
            platform=platform,
            description=description,
            output_dir=Path(output_dir),
            image_path=image,
            fixture=fixture,
            bundle_id=bundle_id,
            app_path=app_path,
        )
        console.print(f"[green]Created incident:[/green] {incident.incident_id}")
        console.print(f"  Platform: {incident.platform.value}")
        console.print(f"  Status:   {incident.status.value}")
        console.print(f"  Path:     {Path(output_dir) / incident.incident_id}")
    except (ValueError, FileNotFoundError) as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@main.command()
@click.option("--incident-id", "-i", required=True, help="Incident ID to run")
@click.option("--output-dir", default="runs", help="Output directory")
@click.option("--adapter", default="maestro", help="Automation adapter")
@click.option("--planner", default="rule", help="Planner type (rule, llm)")
@click.option("--skip-preflight", is_flag=True, help="Skip environment checks")
@click.option("--skip-scoring", is_flag=True, help="Skip screenshot scoring")
def run(
    incident_id: str,
    output_dir: str,
    adapter: str,
    planner: str,
    skip_preflight: bool,
    skip_scoring: bool,
) -> None:
    """Run reproduction flows for an incident."""
    from pathlib import Path

    from retracer.config import Config
    from retracer.intake.submit import load_incident
    from retracer.models.pipeline_context import PipelineContext
    from retracer.pipeline import execute_pipeline

    try:
        out = Path(output_dir)
        incident = load_incident(incident_id, out)

        config = Config(
            output_dir=out,
            default_adapter=adapter,
            planner_type=planner,
            preflight_enabled=not skip_preflight,
            scoring_enabled=not skip_scoring,
        )

        ctx = PipelineContext(incident=incident, output_dir=out)
        ctx = execute_pipeline(ctx, config)

        # Print summary
        console.print(f"\n[green]Pipeline complete:[/green] {incident_id}")
        console.print(f"  Runs:    {len(ctx.runs)}")
        console.print(f"  Scores:  {len(ctx.scores)}")
        if ctx.best_score:
            console.print(f"  Best:    {ctx.best_score.confidence.value} ({ctx.best_score.score:.3f})")
        if ctx.report and ctx.report.report_path:
            console.print(f"  Report:  {ctx.report.report_path}")

    except (ValueError, FileNotFoundError) as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@main.command()
@click.option("--incident-id", "-i", required=True, help="Incident ID")
@click.option("--output-dir", default="runs", help="Output directory")
def report(incident_id: str, output_dir: str) -> None:
    """View the report for an incident."""
    from pathlib import Path

    report_path = Path(output_dir) / incident_id / "report.md"
    if not report_path.exists():
        console.print(f"[red]No report found for {incident_id}[/red]")
        console.print(f"Run `retracer run --incident-id {incident_id}` first.")
        sys.exit(1)

    console.print(report_path.read_text())


@main.command()
@click.option("--platform", "-p", default=None, help="Check specific platform only")
def doctor(platform: str | None) -> None:
    """Check environment readiness."""
    from retracer.environment.preflight import doctor_check

    results = doctor_check(platform)

    for platform_name, result in results.items():
        table = Table(title=f"Environment: {platform_name}")
        table.add_column("Check", style="bold")
        table.add_column("Result")

        for msg in result.messages:
            if "OK" in msg or ":" in msg:
                parts = msg.split(":", 1)
                check_name = parts[0].strip()
                check_result = parts[1].strip() if len(parts) > 1 else msg
                style = "green" if "OK" in check_result or "not applicable" in check_result else "red"
                table.add_row(check_name, f"[{style}]{check_result}[/{style}]")
            else:
                table.add_row(msg, "")

        status = "[green]READY[/green]" if result.passed else "[red]NOT READY[/red]"
        table.add_row("Overall", status)
        console.print(table)
        console.print()


@main.command()
@click.option("--platform", "-p", multiple=True, help="Platforms to set up (default: all)")
@click.option("--output-dir", default="runs", help="Output directory")
@click.option("--no-install", is_flag=True, help="Only check, don't install missing tools")
def setup(platform: tuple[str, ...], output_dir: str, no_install: bool) -> None:
    """Bootstrap the environment — install tools, create directories, validate setup."""
    from pathlib import Path

    from retracer.environment.setup import run_setup

    project_root = Path.cwd()
    platforms = list(platform) if platform else None

    console.print("[bold]Bug Agent Setup[/bold]\n")

    result = run_setup(
        project_root=project_root,
        output_dir=Path(output_dir),
        platforms=platforms,
        install_tools=not no_install,
    )

    table = Table(title="Setup Results")
    table.add_column("Step", style="bold")
    table.add_column("Status")
    table.add_column("Details")

    status_styles = {
        "ok": ("green", "✅"),
        "installed": ("cyan", "📦"),
        "skipped": ("dim", "⏭"),
        "failed": ("red", "❌"),
        "pending": ("yellow", "⏳"),
    }

    for step in result.steps:
        style, icon = status_styles.get(step.status, ("white", "?"))
        table.add_row(
            step.name,
            f"[{style}]{icon} {step.status}[/{style}]",
            step.message,
        )

    console.print(table)
    console.print()

    if result.success:
        console.print("[bold green]Setup complete![/bold green] Run [bold]retracer doctor[/bold] to verify.")
    else:
        failed = [s for s in result.steps if s.status == "failed"]
        console.print(f"[bold red]{len(failed)} step(s) need attention.[/bold red]")
        for s in failed:
            console.print(f"  [red]•[/red] {s.name}: {s.message}")
        sys.exit(1)


if __name__ == "__main__":
    main()

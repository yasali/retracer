"""Maestro automation adapter — MVP runner for black-box UI flows."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from retracer.config import Config
from retracer.models.artifact_ref import ArtifactKind, ArtifactRef
from retracer.models.incident import Incident
from retracer.models.run_result import RunResult, RunStatus
from retracer.runners.base import register_runner
from retracer.utils.fs import ensure_dir, write_json
from retracer.utils.shell import run_cmd

logger = logging.getLogger(__name__)


class MaestroRunner:
    """Execute Maestro YAML flows via subprocess."""

    @property
    def name(self) -> str:
        return "maestro"

    def run_flow(
        self,
        *,
        flow_id: str,
        run_id: str,
        incident: Incident,
        output_dir: Path,
        config: Config,
    ) -> RunResult:
        started_at = datetime.now(timezone.utc)
        ensure_dir(output_dir)
        screenshots_dir = ensure_dir(output_dir / "screenshots")
        logs_dir = ensure_dir(output_dir / "logs")

        # Resolve flow file
        flow_path = self._resolve_flow(flow_id, incident.platform.value, config)

        # Pre-run screenshot
        pre_screenshot = self._capture_screenshot(screenshots_dir, "pre_flow", incident)

        # Execute Maestro flow
        cmd = [
            "maestro", "test",
            str(flow_path),
            "--format", "junit",
            "--output", str(logs_dir / "report.xml"),
        ]

        env = {}
        if incident.fixture:
            env["FIXTURE"] = incident.fixture
        if incident.bundle_id:
            env["APP_ID"] = incident.bundle_id

        result = run_cmd(cmd, timeout=config.run_timeout, env=env if env else None)

        # Save stdout/stderr logs
        stdout_log = logs_dir / "stdout.log"
        stderr_log = logs_dir / "stderr.log"
        stdout_log.write_text(result.stdout)
        stderr_log.write_text(result.stderr)

        # Post-run screenshot
        post_screenshot = self._capture_screenshot(screenshots_dir, "post_flow", incident)

        # Build artifact lists
        screenshots: list[ArtifactRef] = []
        if pre_screenshot:
            screenshots.append(pre_screenshot)
        if post_screenshot:
            screenshots.append(post_screenshot)

        # Gather any Maestro-generated screenshots
        for img in screenshots_dir.glob("*.png"):
            if img.name not in ("pre_flow.png", "post_flow.png"):
                screenshots.append(ArtifactRef(
                    path=img, kind=ArtifactKind.SCREENSHOT, label=img.stem, step="maestro",
                ))

        logs = [
            ArtifactRef(path=stdout_log, kind=ArtifactKind.LOG, label="stdout"),
            ArtifactRef(path=stderr_log, kind=ArtifactKind.LOG, label="stderr"),
        ]

        # Determine status
        if result.returncode == 0:
            status = RunStatus.PASSED
        elif result.stderr == "timeout":
            status = RunStatus.TIMEOUT
        else:
            status = RunStatus.FAILED

        finished_at = datetime.now(timezone.utc)

        run_result = RunResult(
            run_id=run_id,
            incident_id=incident.incident_id,
            adapter=self.name,
            platform=incident.platform.value,
            flow_id=flow_id,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            exit_code=result.returncode,
            screenshots=screenshots,
            logs=logs,
            metadata={"flow_path": str(flow_path)},
        )

        # Persist result
        write_json(output_dir / "result.json", run_result.model_dump(mode="json"))
        logger.info("Flow %s completed: %s (exit=%d)", flow_id, status.value, result.returncode)

        return run_result

    def _resolve_flow(self, flow_id: str, platform: str, config: Config) -> Path:
        """Find the flow YAML file by ID, searching platform-specific then common dirs."""
        search_dirs = [
            config.flows_dir / "maestro" / platform,
            config.flows_dir / "maestro" / "common",
        ]

        for d in search_dirs:
            candidate = d / f"{flow_id}.yaml"
            if candidate.exists():
                return candidate

        raise FileNotFoundError(
            f"Flow not found: {flow_id}. "
            f"Searched: {[str(d) for d in search_dirs]}"
        )

    def _capture_screenshot(
        self, output_dir: Path, name: str, incident: Incident
    ) -> ArtifactRef | None:
        """Capture a simulator screenshot via platform handler."""
        from retracer.platforms.base import get_platform

        platform = get_platform(incident.platform.value)
        if not platform.capture_screenshot:
            return None

        output_path = str(output_dir / f"{name}.png")
        result_path = platform.capture_screenshot(output_path)
        if result_path:
            return ArtifactRef(
                path=result_path, kind=ArtifactKind.SCREENSHOT, label=name, step=name,
            )
        return None


# Register on import
register_runner(MaestroRunner())

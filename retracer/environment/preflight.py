"""Preflight environment validation.

Checks that the required tools and devices are available before
running the pipeline. Platform-specific checks are delegated to
the PlatformConfig — this module only orchestrates.
"""

from __future__ import annotations

import logging

from retracer.config import Config
from retracer.models.incident import Incident
from retracer.models.pipeline_context import PreflightResult
import retracer.platforms  # noqa: F401 — triggers platform registration
from retracer.platforms.base import get_platform
from retracer.utils.shell import check_tool_available

logger = logging.getLogger(__name__)


def run_preflight(incident: Incident, config: Config) -> PreflightResult:
    """Run all preflight checks for the incident's platform."""
    platform = get_platform(incident.platform.value)
    checks: dict[str, bool] = {}
    messages: list[str] = []

    # Check required CLI tools
    for tool in platform.required_tools:
        available = check_tool_available(tool)
        checks[f"tool:{tool}"] = available
        if not available:
            messages.append(f"Required tool not found: {tool}")

    # Check for booted device/simulator
    if platform.discover_devices:
        devices = platform.discover_devices()
        has_device = len(devices) > 0
        checks["device_available"] = has_device
        if not has_device:
            messages.append(
                f"No booted {platform.display_name} device found. "
                f"Please boot a simulator before running."
            )
        else:
            logger.info("Found %d booted device(s): %s", len(devices), devices)
    else:
        checks["device_available"] = True  # Platform doesn't require device discovery

    # Check app is running (best-effort)
    if incident.bundle_id and platform.check_app_running:
        running = platform.check_app_running(incident.bundle_id)
        checks["app_running"] = running
        if not running:
            messages.append(
                f"App {incident.bundle_id} does not appear to be running. "
                f"Please launch it manually or use --app-path."
            )
    else:
        checks["app_running"] = True  # Skip if no bundle_id or no checker

    passed = all(checks.values())
    return PreflightResult(passed=passed, checks=checks, messages=messages)


def doctor_check(platform_name: str | None = None) -> dict[str, PreflightResult]:
    """Run preflight for one or all platforms. Used by `retracer doctor`."""
    from retracer.platforms.base import available_platforms

    platforms_to_check = [platform_name] if platform_name else available_platforms()
    results = {}

    for pname in platforms_to_check:
        platform = get_platform(pname)
        checks: dict[str, bool] = {}
        messages: list[str] = []

        for tool in platform.required_tools:
            available = check_tool_available(tool)
            checks[f"tool:{tool}"] = available
            if not available:
                messages.append(f"{tool}: not found")
            else:
                messages.append(f"{tool}: OK")

        if platform.discover_devices:
            devices = platform.discover_devices()
            checks["devices"] = len(devices) > 0
            messages.append(f"Booted devices: {len(devices)}")
        else:
            messages.append("Device discovery: not applicable")

        results[pname] = PreflightResult(
            passed=all(checks.values()),
            checks=checks,
            messages=messages,
        )

    return results

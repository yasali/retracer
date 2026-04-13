"""tvOS platform configuration and handlers."""

from __future__ import annotations

from retracer.platforms.base import PlatformConfig, register_platform
from retracer.utils.shell import run_cmd


def discover_tvos_simulators() -> list[dict]:
    """List booted tvOS simulators via xcrun simctl."""
    result = run_cmd(["xcrun", "simctl", "list", "devices", "booted", "-j"])
    if result.returncode != 0:
        return []

    import json

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    devices = []
    for runtime, device_list in data.get("devices", {}).items():
        if "tvOS" not in runtime:
            continue
        for dev in device_list:
            if dev.get("state") == "Booted":
                devices.append({
                    "device_id": dev["udid"],
                    "name": dev["name"],
                    "is_booted": True,
                    "runtime": runtime,
                })
    return devices


tvos_config = register_platform(PlatformConfig(
    name="tvos",
    display_name="tvOS Simulator",
    default_automation="maestro",
    flow_extensions=(".yaml",),
    flow_dirs=("flows/maestro/common", "flows/maestro/tvos"),
    discover_devices=discover_tvos_simulators,
    # Reuse iOS simctl functions — same tool, different runtime filter
    install_app=None,  # tvOS install uses same simctl, can share ios.install_ios_app
    launch_app=None,
    capture_screenshot=None,
    check_app_running=None,
    required_tools=("xcrun", "maestro"),
    supports_simulator=True,
    supports_real_device=False,
))

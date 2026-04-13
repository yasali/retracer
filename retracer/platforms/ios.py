"""iOS platform configuration and handlers."""

from __future__ import annotations

from retracer.platforms.base import PlatformConfig, register_platform
from retracer.utils.shell import run_cmd


def discover_ios_simulators() -> list[dict]:
    """List booted iOS simulators via xcrun simctl."""
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
        if "iOS" not in runtime:
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


def install_ios_app(app_path: str, device_id: str | None = None) -> bool:
    """Install a .app bundle into an iOS simulator."""
    cmd = ["xcrun", "simctl", "install"]
    cmd.append(device_id or "booted")
    cmd.append(app_path)
    result = run_cmd(cmd)
    return result.returncode == 0


def launch_ios_app(bundle_id: str, device_id: str | None = None) -> bool:
    """Launch an app in the iOS simulator by bundle ID."""
    cmd = ["xcrun", "simctl", "launch"]
    cmd.append(device_id or "booted")
    cmd.append(bundle_id)
    result = run_cmd(cmd)
    return result.returncode == 0


def capture_ios_screenshot(output_path: str, device_id: str | None = None):
    """Capture a screenshot from the iOS simulator."""
    from pathlib import Path

    cmd = ["xcrun", "simctl", "io"]
    cmd.append(device_id or "booted")
    cmd.extend(["screenshot", output_path])
    result = run_cmd(cmd)
    if result.returncode == 0:
        return Path(output_path)
    return None


def check_ios_app_running(bundle_id: str, device_id: str | None = None) -> bool:
    """Best-effort check if an app appears to be running."""
    cmd = ["xcrun", "simctl", "get_app_container"]
    cmd.append(device_id or "booted")
    cmd.append(bundle_id)
    result = run_cmd(cmd)
    return result.returncode == 0


ios_config = register_platform(PlatformConfig(
    name="ios",
    display_name="iOS Simulator",
    default_automation="maestro",
    flow_extensions=(".yaml",),
    flow_dirs=("flows/maestro/common", "flows/maestro/ios"),
    discover_devices=discover_ios_simulators,
    install_app=install_ios_app,
    launch_app=launch_ios_app,
    capture_screenshot=capture_ios_screenshot,
    check_app_running=check_ios_app_running,
    required_tools=("xcrun", "maestro"),
    supports_simulator=True,
    supports_real_device=False,
))

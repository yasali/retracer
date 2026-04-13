"""Simctl automation adapter — uses xcrun simctl directly for tvOS and iOS.

Maestro cannot drive tvOS simulators (its XCTest driver only supports iOS).
This adapter uses Apple's simctl CLI which works for ALL simulator types.

For UI interaction (button presses, d-pad navigation), this adapter sends
keyboard events to the Simulator.app window via macOS CGEvent API.
The tvOS Simulator maps keyboard keys to Apple TV Remote buttons:
  Arrow keys → D-pad | Return → Select | Escape → Menu | Space → Play/Pause

Capabilities:
- Launch/terminate apps
- Send button presses (tvOS remote: up/down/left/right/select/menu/home)
- Take screenshots
- Open URLs (deep links)

This is the recommended runner for tvOS. It also works for iOS as a fallback
when Maestro is unavailable.

NOTE: Button presses require macOS Accessibility permission for the terminal app.
      System Settings → Privacy & Security → Accessibility → enable Terminal/iTerm.
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
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

# Map Apple TV Remote buttons → macOS key codes (CGEvent virtual key codes)
# The tvOS Simulator maps these keyboard keys to the Siri Remote d-pad
BUTTON_KEY_CODES: dict[str, int] = {
    "up": 126,         # Arrow Up
    "down": 125,       # Arrow Down
    "left": 123,       # Arrow Left
    "right": 124,      # Arrow Right
    "select": 36,      # Return/Enter
    "menu": 53,        # Escape
    "home": 115,       # Home key (Fn+Left)
    "play_pause": 49,  # Space
}


def _send_key_to_simulator(key_code: int) -> bool:
    """Send a keyboard event to the Simulator.app using CGEvent.

    Returns True if the event was posted successfully.
    Requires macOS Accessibility permission for the calling process.
    """
    try:
        import Quartz  # pyobjc-framework-Quartz

        # Bring Simulator to front
        for app in Quartz.NSWorkspace.sharedWorkspace().runningApplications():
            if app.bundleIdentifier() == "com.apple.iphonesimulator":
                app.activateWithOptions_(Quartz.NSApplicationActivateIgnoringOtherApps)
                break
        else:
            logger.warning("Simulator.app not found in running applications")
            return False

        time.sleep(0.15)  # let Simulator come to front

        # Create and post key down + key up events
        key_down = Quartz.CGEventCreateKeyboardEvent(None, key_code, True)
        key_up = Quartz.CGEventCreateKeyboardEvent(None, key_code, False)

        if key_down is None or key_up is None:
            logger.warning("Failed to create CGEvent — check Accessibility permissions")
            return False

        Quartz.CGEventPost(Quartz.kCGHIDEventTap, key_down)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, key_up)
        time.sleep(0.1)  # small pause to let the event register
        return True

    except ImportError:
        logger.error("pyobjc-framework-Quartz not installed. Run: pip install pyobjc-framework-Quartz")
        return False
    except Exception as e:
        logger.error("Failed to send key event: %s", e)
        return False


class SimctlRunner:
    """Drive simulators directly via xcrun simctl."""

    @property
    def name(self) -> str:
        return "simctl"

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

        device_id = self._get_booted_device(incident.platform.value)
        bundle_id = incident.bundle_id

        log_lines: list[str] = []
        screenshots: list[ArtifactRef] = []
        all_ok = True

        # Load flow steps
        flow_path = self._resolve_flow(flow_id, incident.platform.value, config)
        steps = self._parse_flow(flow_path)

        log_lines.append(f"Device: {device_id}")
        log_lines.append(f"Bundle: {bundle_id}")
        log_lines.append(f"Flow: {flow_id} ({len(steps)} steps)")
        log_lines.append("")

        for i, step in enumerate(steps):
            step_name = step.get("action", "unknown")
            log_lines.append(f"--- Step {i + 1}: {step_name} ---")
            logger.info("[%s] Step %d/%d: %s", run_id, i + 1, len(steps), step_name)

            try:
                result = self._execute_step(
                    step, device_id, bundle_id, screenshots_dir, i + 1
                )
                log_lines.append(f"  Result: {result}")

                # Collect any screenshot from this step
                if result.get("screenshot"):
                    ss_path = Path(result["screenshot"])
                    screenshots.append(ArtifactRef(
                        path=ss_path,
                        kind=ArtifactKind.SCREENSHOT,
                        label=f"step_{i + 1}_{step_name}",
                        step=step_name,
                    ))
            except Exception as e:
                log_lines.append(f"  ERROR: {e}")
                logger.warning("[%s] Step %d failed: %s", run_id, i + 1, e)
                all_ok = False

            # Small pause between steps to let UI settle
            pause = step.get("pause", 1.0)
            time.sleep(pause)

        # Final screenshot
        final_ss = self._screenshot(device_id, screenshots_dir, "final")
        if final_ss:
            screenshots.append(ArtifactRef(
                path=final_ss, kind=ArtifactKind.SCREENSHOT,
                label="final", step="final",
            ))

        # Save logs
        stdout_log = logs_dir / "stdout.log"
        stdout_log.write_text("\n".join(log_lines))

        logs = [ArtifactRef(path=stdout_log, kind=ArtifactKind.LOG, label="stdout")]

        finished_at = datetime.now(timezone.utc)
        status = RunStatus.PASSED if all_ok else RunStatus.FAILED

        run_result = RunResult(
            run_id=run_id,
            incident_id=incident.incident_id,
            adapter=self.name,
            platform=incident.platform.value,
            flow_id=flow_id,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            exit_code=0 if all_ok else 1,
            screenshots=screenshots,
            logs=logs,
            metadata={"device_id": device_id, "flow_path": str(flow_path)},
        )

        write_json(output_dir / "result.json", run_result.model_dump(mode="json"))
        logger.info("Flow %s completed: %s (%d screenshots)", flow_id, status.value, len(screenshots))
        return run_result

    def _get_booted_device(self, platform: str) -> str:
        """Find a booted simulator UDID for the platform."""
        result = run_cmd(["xcrun", "simctl", "list", "devices", "booted", "-j"], timeout=10)
        if result.returncode != 0:
            raise RuntimeError("Failed to list booted simulators")

        data = json.loads(result.stdout)
        runtime_key = "iOS" if platform == "ios" else "tvOS"

        for runtime, devices in data.get("devices", {}).items():
            if runtime_key not in runtime:
                continue
            for dev in devices:
                if dev.get("state") == "Booted":
                    logger.info("Using device: %s (%s)", dev["name"], dev["udid"])
                    return dev["udid"]

        raise RuntimeError(f"No booted {runtime_key} simulator found")

    def _resolve_flow(self, flow_id: str, platform: str, config: Config) -> Path:
        """Find the flow JSON file."""
        search_dirs = [
            config.flows_dir / "simctl" / platform,
            config.flows_dir / "simctl" / "common",
        ]
        for d in search_dirs:
            candidate = d / f"{flow_id}.json"
            if candidate.exists():
                return candidate

        raise FileNotFoundError(
            f"Flow not found: {flow_id}. Searched: {[str(d) for d in search_dirs]}"
        )

    def _parse_flow(self, flow_path: Path) -> list[dict]:
        """Load flow steps from JSON."""
        data = json.loads(flow_path.read_text())
        return data.get("steps", [])

    def _execute_step(
        self,
        step: dict,
        device_id: str,
        bundle_id: str | None,
        screenshots_dir: Path,
        step_num: int,
    ) -> dict:
        """Execute a single flow step via simctl."""
        action = step["action"]

        if action == "launch":
            bid = step.get("bundle_id") or bundle_id
            if not bid:
                return {"status": "skipped", "reason": "no bundle_id"}
            result = run_cmd(
                ["xcrun", "simctl", "launch", device_id, bid], timeout=15
            )
            return {"status": "ok" if result.returncode == 0 else "failed",
                    "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}

        elif action == "terminate":
            bid = step.get("bundle_id") or bundle_id
            if not bid:
                return {"status": "skipped"}
            result = run_cmd(
                ["xcrun", "simctl", "terminate", device_id, bid], timeout=10
            )
            return {"status": "ok" if result.returncode == 0 else "failed"}

        elif action == "screenshot":
            label = step.get("label", f"step_{step_num}")
            ss = self._screenshot(device_id, screenshots_dir, label)
            return {"status": "ok", "screenshot": str(ss)} if ss else {"status": "failed"}

        elif action == "press":
            button = step.get("button", "select")
            return self._press_button(device_id, button)

        elif action == "wait":
            secs = step.get("seconds", 2)
            time.sleep(secs)
            return {"status": "ok", "waited": secs}

        elif action == "open_url":
            url = step["url"]
            result = run_cmd(
                ["xcrun", "simctl", "openurl", device_id, url], timeout=10
            )
            return {"status": "ok" if result.returncode == 0 else "failed"}

        else:
            return {"status": "unknown_action", "action": action}

    def _press_button(self, device_id: str, button: str) -> dict:
        """Send a button press to the tvOS/iOS simulator via keyboard events.

        simctl does NOT have a button press API.  We send keyboard events
        to the Simulator.app window using CGEvent.  The tvOS Simulator maps
        arrow keys to the Apple TV Remote d-pad.
        """
        key_code = BUTTON_KEY_CODES.get(button)
        if key_code is None:
            return {"status": "unknown_button", "button": button}

        ok = _send_key_to_simulator(key_code)
        return {"status": "ok" if ok else "failed", "button": button,
                "method": "CGEvent"}

    def _screenshot(self, device_id: str, output_dir: Path, label: str) -> Path | None:
        """Capture a screenshot from the simulator."""
        path = output_dir / f"{label}.png"
        result = run_cmd(
            ["xcrun", "simctl", "io", device_id, "screenshot", str(path)],
            timeout=10,
        )
        if result.returncode == 0 and path.exists():
            return path
        logger.warning("Screenshot failed: %s", result.stderr.strip())
        return None


register_runner(SimctlRunner())

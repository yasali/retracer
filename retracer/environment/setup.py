"""Environment setup — bootstrap everything needed to run retracer.

Unlike `doctor` (which only checks), `setup` actually creates directories,
installs missing tools, and validates the full environment is ready to go.
"""

from __future__ import annotations

import logging
import platform
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from retracer.utils.fs import ensure_dir
from retracer.utils.shell import check_tool_available, run_cmd

logger = logging.getLogger(__name__)


@dataclass
class SetupStep:
    name: str
    status: str = "pending"  # pending | ok | installed | skipped | failed
    message: str = ""


@dataclass
class SetupResult:
    steps: list[SetupStep] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return all(s.status in ("ok", "installed", "skipped") for s in self.steps)


def run_setup(
    *,
    project_root: Path,
    output_dir: Path,
    platforms: list[str] | None = None,
    install_tools: bool = True,
) -> SetupResult:
    """Run the full setup sequence. Returns a result with per-step status."""
    result = SetupResult()

    # 1. Create directory structure
    result.steps.append(_setup_directories(project_root, output_dir))

    # 2. Check Python version
    result.steps.append(_check_python())

    # 3. Check/install pip dependencies
    result.steps.append(_check_pip_deps())

    # 4. Check Xcode CLI tools (macOS only)
    if platform.system() == "Darwin":
        result.steps.append(_check_xcode_cli())

    # 5. Check/install Maestro
    result.steps.append(_setup_maestro(install=install_tools))

    # 6. Check simulators (macOS only)
    if platform.system() == "Darwin":
        target_platforms = platforms or ["ios", "tvos"]
        for plat in target_platforms:
            result.steps.append(_check_simulators(plat))

    # 7. Create sample fixture if none exist
    result.steps.append(_setup_fixtures(project_root))

    # 8. Validate flows directory
    result.steps.append(_check_flows(project_root))

    return result


def _setup_directories(project_root: Path, output_dir: Path) -> SetupStep:
    """Create all required directories."""
    step = SetupStep(name="Create directories")
    try:
        # Resolve output_dir relative to project_root if not absolute
        resolved_output = output_dir if output_dir.is_absolute() else project_root / output_dir
        dirs = [
            resolved_output,
            project_root / "flows" / "maestro" / "common",
            project_root / "flows" / "maestro" / "ios",
            project_root / "flows" / "maestro" / "tvos",
            project_root / "fixtures" / "accounts",
        ]
        created = []
        for d in dirs:
            if not d.exists():
                ensure_dir(d)
                created.append(str(d))

        if created:
            step.status = "installed"
            step.message = f"Created: {', '.join(created)}"
        else:
            step.status = "ok"
            step.message = "All directories exist"
    except Exception as e:
        step.status = "failed"
        step.message = str(e)
    return step


def _check_python() -> SetupStep:
    """Verify Python version is 3.11+."""
    step = SetupStep(name="Python version")
    import sys

    major, minor = sys.version_info[:2]
    if major >= 3 and minor >= 11:
        step.status = "ok"
        step.message = f"Python {major}.{minor}"
    else:
        step.status = "failed"
        step.message = f"Python {major}.{minor} found, need 3.11+"
    return step


def _check_pip_deps() -> SetupStep:
    """Check that core dependencies are importable."""
    step = SetupStep(name="Python dependencies")
    missing = []

    for mod in ["pydantic", "click", "rich"]:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)

    if missing:
        step.status = "failed"
        step.message = f"Missing: {', '.join(missing)}. Run: pip install {' '.join(missing)}"
    else:
        step.status = "ok"
        step.message = "pydantic, click, rich"

    # Check optional deps
    optional_available = []
    for mod, label in [("PIL", "Pillow (scoring)"), ("pytesseract", "OCR"), ("openai", "LLM")]:
        try:
            __import__(mod)
            optional_available.append(label)
        except ImportError:
            pass

    if optional_available:
        step.message += f" | optional: {', '.join(optional_available)}"

    return step


def _check_xcode_cli() -> SetupStep:
    """Check Xcode command line tools are installed."""
    step = SetupStep(name="Xcode CLI tools")

    if check_tool_available("xcrun"):
        step.status = "ok"
        step.message = "xcrun available"
    else:
        step.status = "failed"
        step.message = "Not found. Run: xcode-select --install"
    return step


def _setup_maestro(*, install: bool) -> SetupStep:
    """Check if Maestro is installed, optionally install it."""
    step = SetupStep(name="Maestro CLI")

    if check_tool_available("maestro"):
        # Get version
        ver = run_cmd(["maestro", "--version"], timeout=10)
        version_str = ver.stdout.strip() if ver.returncode == 0 else "unknown"
        step.status = "ok"
        step.message = f"Installed ({version_str})"
        return step

    if not install:
        step.status = "failed"
        step.message = "Not found. Run: curl -Ls 'https://get.maestro.mobile.dev' | bash"
        return step

    # Attempt to install Maestro
    logger.info("Installing Maestro CLI...")
    if platform.system() == "Darwin":
        # Try brew first
        if check_tool_available("brew"):
            result = run_cmd(["brew", "install", "maestro"], timeout=300)
            if result.returncode == 0:
                step.status = "installed"
                step.message = "Installed via Homebrew"
                return step

    # Fallback to official installer
    result = run_cmd(
        ["bash", "-c", "curl -Ls 'https://get.maestro.mobile.dev' | bash"],
        timeout=120,
    )
    if result.returncode == 0:
        step.status = "installed"
        step.message = "Installed via official installer"
    else:
        step.status = "failed"
        step.message = (
            f"Auto-install failed. Manual install: "
            f"curl -Ls 'https://get.maestro.mobile.dev' | bash\n"
            f"Error: {result.stderr[:200]}"
        )
    return step


def _check_simulators(plat: str) -> SetupStep:
    """Check for available simulators for a given platform."""
    step = SetupStep(name=f"Simulators ({plat})")

    result = run_cmd(["xcrun", "simctl", "list", "devices", "-j"], timeout=15)
    if result.returncode != 0:
        step.status = "failed"
        step.message = "Could not list simulators"
        return step

    import json

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        step.status = "failed"
        step.message = "Could not parse simulator list"
        return step

    runtime_key = "iOS" if plat == "ios" else "tvOS"
    available = []
    booted = []

    for runtime, devices in data.get("devices", {}).items():
        if runtime_key not in runtime:
            continue
        for dev in devices:
            available.append(dev["name"])
            if dev.get("state") == "Booted":
                booted.append(dev["name"])

    if not available:
        step.status = "failed"
        step.message = f"No {runtime_key} simulators found. Open Xcode → Settings → Platforms to download."
    elif booted:
        step.status = "ok"
        step.message = f"{len(available)} available, {len(booted)} booted: {', '.join(booted[:3])}"
    else:
        step.status = "ok"
        step.message = f"{len(available)} available (none booted — boot one before running)"
    return step


def _setup_fixtures(project_root: Path) -> SetupStep:
    """Ensure at least one example fixture exists."""
    step = SetupStep(name="Fixtures")
    fixtures_dir = project_root / "fixtures" / "accounts"

    existing = list(fixtures_dir.glob("*.json")) if fixtures_dir.exists() else []
    if existing:
        step.status = "ok"
        step.message = f"{len(existing)} fixture(s) found"
    else:
        step.status = "ok"
        step.message = "No fixtures (optional — add to fixtures/accounts/)"
    return step


def _check_flows(project_root: Path) -> SetupStep:
    """Check that flow YAML files exist."""
    step = SetupStep(name="Maestro flows")
    flows_dir = project_root / "flows" / "maestro"

    if not flows_dir.exists():
        step.status = "failed"
        step.message = "flows/maestro/ directory not found"
        return step

    yamls = list(flows_dir.rglob("*.yaml"))
    if yamls:
        step.status = "ok"
        step.message = f"{len(yamls)} flow file(s) found"
    else:
        step.status = "failed"
        step.message = "No .yaml flow files found in flows/maestro/"
    return step

# Retracer

**Platform-agnostic UI bug reproduction and triage tool.**

Retracer automates the process of reproducing UI bugs: accept a screenshot and/or description, run candidate UI flows against a running app, capture evidence, score similarity, and generate structured reports.

## Architecture

The tool is built around a **pipeline of pure functions** with pluggable adapters at every stage:

```
intake → preflight → plan → execute → score → report
```

Each stage operates on a shared `PipelineContext` and can be swapped independently. Platform support (iOS, tvOS, Android, Web) is driven by `PlatformConfig` dataclasses — adding a new platform means writing a config, not rewriting the pipeline.

See [`docs/CONTRACTS.md`](docs/CONTRACTS.md) for the canonical schemas and interfaces.

## Prerequisites

- Python 3.11+
- macOS with Xcode and Simulator (for iOS/tvOS targets)
- A booted simulator or connected device for the target platform
- `pyobjc-framework-Quartz` (installed automatically — used for tvOS remote button presses)

## Installation

```bash
# Clone and install
git clone <repo-url> && cd retracer
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# Bootstrap the environment (creates directories, checks tools, installs Maestro)
retracer setup

# Verify everything is ready
retracer doctor
```

## Quick Start

### 1. Boot a simulator

```bash
# List available simulators
xcrun simctl list devices available

# Boot one (example — use your own device type)
xcrun simctl boot "Apple TV 4K (3rd generation)"
```

### 2. Submit an incident

```bash
retracer submit \
  --platform tvos \
  --bundle-id com.example.myapp.debug \
  --description "Profile menu overlays the sport home screen"
```

This creates an incident manifest under `runs/inc_NNNN/manifest.json`.

### 3. Run the pipeline

```bash
retracer run --incident-id inc_0001
```

Or run directly from a script:

```python
from retracer.pipeline import execute_pipeline, DEFAULT_STAGES
from retracer.models.pipeline_context import PipelineContext
from retracer.models.incident import Incident, Platform
from retracer.config import Config

incident = Incident(
    incident_id="inc_0001",
    title="Profile overlay on sport screen",
    platform=Platform.TVOS,
    bundle_id="com.example.myapp.debug",
    description="Profile menu overlays the sport home screen",
)

config = Config(default_adapter="simctl")
ctx = PipelineContext(incident=incident)
result = execute_pipeline(ctx, config, DEFAULT_STAGES)
```

### 4. View results

```bash
# Read the markdown report
cat runs/inc_0001/report.md

# Open a captured screenshot
open runs/inc_0001/run_001/screenshots/after_launch.png

# Machine-readable bundle
cat runs/inc_0001/bundle.json
```

## Automation Adapters

| Adapter   | Platforms       | How it works                                                  |
|-----------|-----------------|---------------------------------------------------------------|
| `simctl`  | iOS, tvOS       | Drives simulators via `xcrun simctl`. Button presses use CGEvent keyboard events to the Simulator window. **Recommended for tvOS.** |
| `maestro` | iOS             | Uses [Maestro](https://maestro.mobile.dev) YAML flows. Does **not** support tvOS. |

Set the adapter in Config or CLI:

```bash
retracer run --incident-id inc_0001 --adapter simctl
```

### tvOS Button Mapping

The simctl adapter sends keyboard events that the tvOS Simulator maps to the Apple TV Remote:

| Button      | Key            |
|-------------|----------------|
| D-pad Up    | Arrow Up       |
| D-pad Down  | Arrow Down     |
| D-pad Left  | Arrow Left     |
| D-pad Right | Arrow Right    |
| Select      | Return/Enter   |
| Menu        | Escape         |
| Play/Pause  | Space          |

> **Note:** Button presses require macOS Accessibility permission for the terminal app.
> System Settings → Privacy & Security → Accessibility → enable Terminal (or iTerm).

## Writing Flows

Flows are JSON files that describe a sequence of UI actions. They live under `flows/simctl/<platform>/` or `flows/simctl/common/`.

```json
{
  "description": "Launch the app and take a screenshot",
  "steps": [
    {"action": "launch"},
    {"action": "wait", "seconds": 3},
    {"action": "screenshot", "label": "after_launch"}
  ]
}
```

### Available actions

| Action      | Parameters                         | Description                        |
|-------------|------------------------------------|------------------------------------|
| `launch`    | `bundle_id` (optional, uses incident default) | Launch or foreground the app |
| `terminate` | `bundle_id` (optional)             | Kill the app                       |
| `press`     | `button` (up/down/left/right/select/menu) | Send a remote button press   |
| `wait`      | `seconds` (default: 2)            | Pause between steps                |
| `screenshot`| `label`                            | Capture a screenshot               |
| `open_url`  | `url`                              | Open a deep link                   |

### Flow resolution order

1. `flows/simctl/<platform>/<flow_id>.json` (platform-specific)
2. `flows/simctl/common/<flow_id>.json` (shared across platforms)

## Pipeline Stages

| Stage       | What it does                                                    |
|-------------|----------------------------------------------------------------|
| `preflight` | Validates tools, devices, and environment via PlatformConfig   |
| `planning`  | Selects candidate flows by matching incident keywords to flow tags |
| `execution` | Runs each flow through the automation adapter, captures screenshots |
| `scoring`   | Compares screenshots to a reference image (if provided)         |
| `reporting` | Generates a markdown report + machine-readable `bundle.json`   |

## CLI Commands

```
retracer setup       # Bootstrap environment
retracer doctor      # Check environment health
retracer submit      # Create an incident
retracer run         # Run the pipeline for an incident
retracer report      # View/regenerate an incident report
```

## Optional Dependencies

```bash
pip install -e ".[scoring]"   # Pillow for screenshot comparison
pip install -e ".[ocr]"       # OCR-based text extraction scoring
pip install -e ".[llm]"       # LLM-powered flow planning
pip install -e ".[dev]"       # Development tools
```

## Project Structure

```
retracer/
  cli.py                  # CLI entry point
  config.py               # Global configuration
  pipeline.py             # Explicit pipeline chain
  security.py             # Centralized input validation
  models/                 # Canonical data schemas
  platforms/              # Platform configs (iOS, tvOS, Android, Web)
  environment/            # Device/simulator detection and preflight
  planner/                # Flow selection (rule-based, LLM-ready)
  runners/                # Automation adapters (simctl, Maestro)
  artifacts/              # Storage, screenshots, caching
  scoring/                # Screenshot similarity with confidence labels
  reporting/              # Markdown reports and bundles
flows/
  simctl/
    common/               # Shared flows (launch, navigate, etc.)
    tvos/                 # tvOS-specific flows
    ios/                  # iOS-specific flows
  maestro/
    common/               # Maestro YAML flows (iOS only)
runs/                     # Pipeline output (one folder per incident)
docs/
  CONTRACTS.md            # Canonical schemas and extension points
  architecture.md         # Original architecture notes
```

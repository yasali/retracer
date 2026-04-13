# Retracer Contracts

> **Every module, adapter, and prompt in this project must conform to these contracts.**
> This is the single source of truth for data shapes and interfaces.

---

## 1. Pipeline Stages

The pipeline is a linear chain of pure functions. Each stage takes `(PipelineContext, Config)` and returns `PipelineContext`. Stages must not mutate fields they don't own.

```
intake → preflight → plan → execute → score → report
```

| Stage | Input | Output (added to context) | Can skip? |
|-------|-------|--------------------------|-----------|
| **intake** | CLI args | `PipelineContext.incident` | No |
| **preflight** | incident.platform | `PipelineContext.preflight` | Yes (`--skip-preflight`) |
| **plan** | incident.description + platform | `PipelineContext.plan` | No |
| **execute** | plan.flow_ids | `PipelineContext.runs` | No |
| **score** | incident.image_path + runs.screenshots | `PipelineContext.scores` | Yes (`--skip-scoring`) |
| **report** | all above | `PipelineContext.report` | No |

---

## 2. Canonical Data Schemas

### 2.1 Incident

```python
Incident(
    incident_id: str,          # "inc_0001"
    platform: Platform,        # ios | tvos | android | web
    description: str,
    image_path: Path | None,
    fixture: str | None,
    bundle_id: str | None,
    app_path: Path | None,
    notes: str | None,
    status: IncidentStatus,    # submitted | running | completed | failed
    created_at: datetime,
    metadata: dict,
)
```

### 2.2 RunResult

Every automation adapter must produce this exact shape.

```python
RunResult(
    run_id: str,               # "run_001"
    incident_id: str,
    adapter: str,              # "maestro" | "xcuitest" | "appium" | "playwright"
    platform: str,
    flow_id: str,
    status: RunStatus,         # passed | failed | error | timeout
    started_at: datetime,
    finished_at: datetime | None,
    exit_code: int,
    screenshots: list[ArtifactRef],
    logs: list[ArtifactRef],
    ui_tree: dict | None,
    metadata: dict,
)
```

### 2.3 ScoreResult

Every scoring adapter must produce this exact shape.

```python
ScoreResult(
    run_id: str,
    best_match: ArtifactRef | None,
    confidence: Confidence,    # CONFIRMED | LIKELY | POSSIBLE | INCONCLUSIVE
    score: float,              # 0.0 – 1.0
    method: str,               # "structural" | "pixel" | "ocr" | "ml"
    evidence: list[str],       # Human-readable reasons
    metadata: dict,
)
```

### 2.4 ArtifactRef

Universal pointer to any stored file.

```python
ArtifactRef(
    path: Path,
    kind: ArtifactKind,        # screenshot | log | ui_tree | video | report | bundle | other
    label: str,
    step: str | None,
    metadata: dict,
)
```

### 2.5 Confidence Labels

| Label | Meaning | When to use |
|-------|---------|-------------|
| `CONFIRMED` | Visual match + same UI state + same error | Score ≥ 0.85 or manual confirmation |
| `LIKELY` | Structurally similar, flow reached the right screen | Score 0.6–0.85 |
| `POSSIBLE` | Flow ran without error but evidence is weak | Score 0.3–0.6 |
| `INCONCLUSIVE` | Flow failed or evidence doesn't match | Score < 0.3 or no comparison possible |

---

## 3. Adapter Interfaces

### 3.1 AutomationAdapter (Runners)

```python
class AutomationAdapter(Protocol):
    @property
    def name(self) -> str: ...

    def run_flow(
        self,
        *,
        flow_id: str,
        run_id: str,
        incident: Incident,
        output_dir: Path,
        config: Config,
    ) -> RunResult: ...
```

Implementations: `MaestroRunner`, `XCUITestRunner` (future), `AppiumRunner` (future), `PlaywrightRunner` (future).

### 3.2 ScoringAdapter

```python
class ScoringAdapter(Protocol):
    @property
    def name(self) -> str: ...

    def score(
        self,
        *,
        reference: Path,
        candidates: list[ArtifactRef],
        run_id: str,
    ) -> ScoreResult: ...
```

Implementations: `StructuralScorer`, `PixelScorer` (future), `OCRScorer` (future), `MLScorer` (future).

### 3.3 PlannerAdapter

```python
class PlannerAdapter(Protocol):
    @property
    def name(self) -> str: ...

    def plan(
        self,
        *,
        description: str,
        platform: str,
        fixture: str | None = None,
        image_path: str | None = None,
    ) -> PlanResult: ...
```

Implementations: `RuleBasedPlanner`, `LLMPlanner` (future).

### 3.4 PlatformConfig

```python
PlatformConfig(
    name: str,
    display_name: str,
    default_automation: str,
    flow_extensions: tuple[str, ...],
    flow_dirs: tuple[str, ...],
    discover_devices: Callable | None,
    install_app: Callable | None,
    launch_app: Callable | None,
    capture_screenshot: Callable | None,
    check_app_running: Callable | None,
    required_tools: tuple[str, ...],
    supports_simulator: bool,
    supports_real_device: bool,
    metadata: dict,
)
```

Registered platforms: `ios`, `tvos`. Future: `android`, `web`.

---

## 4. File System Conventions

```
runs/
  <incident_id>/
    manifest.json           # Incident data
    reference.png           # Copied reference image (if provided)
    bundle.json             # Machine-readable incident summary
    report.md               # Human-readable report
    run_001/
      result.json           # RunResult
      artifact_index.json   # All artifacts for this run
      screenshots/
        pre_flow.png
        post_flow.png
        *.png               # Adapter-generated screenshots
      logs/
        stdout.log
        stderr.log
    run_002/
      ...
```

---

## 5. Security Boundary

All external input passes through `retracer/security.py`:

| Function | What it guards |
|----------|---------------|
| `validate_path(path, root)` | Directory traversal prevention |
| `validate_path_exists(path)` | File existence check |
| `sanitize_shell_arg(arg)` | Shell injection prevention |
| `redact_secrets(data)` | Credential masking in logs/reports |
| `validate_bundle_id(id)` | Bundle ID format validation |

---

## 6. Extension Points

To add a **new platform**: create `retracer/platforms/<name>.py`, define a `PlatformConfig`, call `register_platform()`.

To add a **new runner**: create `retracer/runners/<name>_runner.py`, implement `AutomationAdapter`, call `register_runner()`.

To add a **new scorer**: create `retracer/scoring/<name>_scorer.py`, implement `ScoringAdapter`, call `register_scorer()`.

To add a **new planner**: create `retracer/planner/<name>_planner.py`, implement `PlannerAdapter`, call `register_planner()`.

To add a **new pipeline stage**: write a function `(PipelineContext, Config) → PipelineContext`, insert it into the stages list.

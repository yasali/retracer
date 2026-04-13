# Architecture Improvements — Lessons from Graphify Applied to Retracer

> Deep analysis of the current retracer architecture, its prompt pipeline, and concrete improvements inspired by Graphify's design patterns. The goal: make retracer a **generalizable tool** that could serve any mobile/UI ecosystem, not just iOS/tvOS.

---

## 1. Executive Summary

Bug-agent is currently designed as a specific iOS/tvOS bug reproduction tool. The architecture is sound for that scope, but it is **tightly coupled to a single ecosystem** in ways that don't need to be. Graphify demonstrates that a tool can support 22 programming languages through data-driven configs, serve 12+ AI platforms through adapter dispatch tables, and maintain a clean pipeline architecture — all without over-engineering.

The core insight: **retracer's pipeline is already close to being generalizable**. With targeted structural changes (not rewrites), it can become a platform-agnostic UI bug reproduction framework where "iOS + Maestro" is just one configuration, and "Android + Appium" or "Web + Playwright" could be another.

---

## 2. What Graphify Gets Right (Patterns to Adopt)

### 2.1 Pipeline Architecture (Unix Philosophy)

Graphify's pipeline is a **linear chain of pure functions**, each in its own module:

```
detect() → extract() → build_graph() → cluster() → analyze() → report() → export()
```

No shared mutable state. Each stage takes plain data in, returns new data out. Any stage can be swapped without breaking the others.

**Bug-agent's equivalent pipeline:**

```
intake() → preflight() → plan() → run() → capture() → score() → report()
```

This is already implicit in the architecture, but it's not formalized. The prompts build it incrementally across phases, which means the pipeline contract is never explicitly defined. **This is the single biggest improvement opportunity.**

### 2.2 Data-Driven Configuration (LanguageConfig Pattern)

Graphify doesn't write a parser per language. It defines a `LanguageConfig` dataclass and a generic walker. New language = new config instance, not new code.

Bug-agent should do the same for **platforms**. Instead of scattering iOS/tvOS logic, define a `PlatformConfig`:

```python
@dataclass
class PlatformConfig:
    name: str                           # "ios", "tvos", "android", "web"
    simulator_cmd: str                  # "xcrun simctl", "emulator", "n/a"
    device_discovery_fn: Callable       # platform-specific device listing
    app_install_fn: Callable | None     # platform-specific install
    screenshot_fn: Callable             # how to capture screenshots
    default_automation: str             # "maestro", "xcuitest", "appium", "playwright"
    flow_extensions: list[str]          # [".yaml"] for Maestro, [".swift"] for XCUITest
```

**Adding Android support** becomes: define a new `PlatformConfig`, implement 3-4 handler functions, done. No new modules needed.

### 2.3 Canonical Data Format

Graphify's strongest glue is its `{nodes, edges}` schema. Every module consumes and produces the same shape. This is what makes swapping components safe.

Bug-agent needs an equivalent: a **canonical incident format** that flows through the entire pipeline. Currently the manifest is defined, but the intermediate data (planner output, run results, scoring) are separate schemas that aren't formally related.

### 2.4 Confidence System (Honesty About Uncertainty)

Graphify tags every relationship as `EXTRACTED`, `INFERRED`, or `AMBIGUOUS`. This is directly applicable to retracer's scoring:

| Confidence | Retracer Meaning |
|-----------|-------------------|
| `CONFIRMED` | Visual match + same UI state + same error |
| `LIKELY` | Screenshots are structurally similar, flow reached the right screen |
| `POSSIBLE` | Flow ran without error but evidence is weak |
| `INCONCLUSIVE` | Flow failed or evidence doesn't match |

This replaces the vague `low/medium/high` scoring in phase-3-prompt-a with a system that is **machine-actionable and human-readable**.

### 2.5 Content-Addressable Caching

Graphify uses `SHA256(content)` to skip re-processing unchanged files. Bug-agent should cache:

- **Flow execution results** keyed by `SHA256(flow_file + app_build_id + fixture)` — if nothing changed, don't re-run
- **Screenshot baselines** for regression detection
- **Scoring results** to avoid re-computing similarity

This becomes critical when retracer scales to CI where re-runs are frequent.

### 2.6 Graceful Degradation

Graphify works at multiple capability levels: no optional deps → basic; add graspologic → better clustering; add MCP → tool server. Bug-agent should adopt this:

| Level | Capabilities |
|-------|-------------|
| Core (no optional deps) | CLI intake, manual flow execution, basic reports |
| + Maestro | Automated black-box flows |
| + XCUITest | Native Apple automation |
| + image scoring (Pillow/OpenCV) | Screenshot comparison |
| + LLM (OpenAI/Claude API) | AI-driven flow planning |
| + CI integration | GitHub Actions, artifact registries |

Each layer adds capability but isn't required. The core always works.

### 2.7 Security as a Boundary

Graphify's `security.py` is a single chokepoint for all input validation. Bug-agent handles sensitive data (account fixtures with passwords, app paths, shell commands) but has no equivalent security boundary. This needs fixing before the tool is used by anyone outside your team.

---

## 3. What Retracer Needs to Change

### 3.1 Formalize the Pipeline Contract

**Current state:** The pipeline is implicit, built across 17 prompts. There's no single place that defines "data flows from A → B → C."

**Proposed:** Create a `pipeline.py` that makes the chain explicit:

```python
@dataclass
class PipelineContext:
    """Canonical data object that flows through every stage."""
    incident: Incident
    preflight: PreflightResult | None = None
    plan: PlanResult | None = None
    runs: list[RunResult] = field(default_factory=list)
    scores: list[ScoreResult] = field(default_factory=list)
    report: ReportResult | None = None

def execute_pipeline(ctx: PipelineContext, config: PipelineConfig) -> PipelineContext:
    ctx = preflight_stage(ctx, config)
    ctx = planning_stage(ctx, config)
    ctx = execution_stage(ctx, config)
    ctx = capture_stage(ctx, config)
    ctx = scoring_stage(ctx, config)
    ctx = reporting_stage(ctx, config)
    return ctx
```

Each stage is a pure function: `(PipelineContext, Config) → PipelineContext`. Any stage can be replaced, skipped, or extended.

**Why this matters for generalization:** A web testing pipeline might skip `preflight` (no simulator to check) and use a different `execution_stage`. The pipeline shape stays the same.

### 3.2 Extract Platform-Specific Logic into Configs

**Current state:** iOS/tvOS is hardcoded in simulator detection, Maestro invocation, and flow paths.

**Proposed:** A `platforms/` directory with pluggable configs:

```
retracer/
  platforms/
    base.py          # PlatformConfig protocol
    ios.py           # iOS-specific: simctl, Maestro flows, .app bundles
    tvos.py          # tvOS-specific: focus navigation, remote simulation
    android.py       # Future: adb, emulator, Appium
    web.py           # Future: browser launch, Playwright/Cypress
```

The CLI gets `--platform ios` and the system loads the right config. All downstream code works against the `PlatformConfig` interface, never against raw `xcrun` calls.

### 3.3 Adapter Layer Needs a Canonical Result Schema

**Current state:** `runners/base.py` defines a protocol, which is good. But there's no standard for what a `RunResult` contains across adapters.

**Proposed:** A strict `RunResult` schema (like Graphify's `{nodes, edges}`):

```python
@dataclass
class RunResult:
    run_id: str
    incident_id: str
    adapter: str                    # "maestro", "xcuitest", "appium"
    platform: str                   # "ios", "tvos", "android", "web"
    flow_id: str
    status: Literal["passed", "failed", "error", "timeout"]
    started_at: datetime
    finished_at: datetime
    exit_code: int
    screenshots: list[ArtifactRef]  # Canonical artifact references
    logs: list[ArtifactRef]
    ui_tree: dict | None            # Platform-specific UI hierarchy
    metadata: dict                  # Adapter-specific extra data
```

Every adapter must produce this exact shape. The scoring and reporting modules never need to know which adapter ran.

### 3.4 Add a Plugin/Hook System for Extensibility

Graphify hooks into 12 AI platforms through a dispatch table. Bug-agent should have hooks for:

- **Pre-run hooks** — fixture setup, app state reset, feature flag configuration
- **Post-run hooks** — artifact upload, notification, CI status update
- **Post-report hooks** — GitHub issue creation, Slack notification, Jira ticket

```python
@dataclass
class PipelineHooks:
    pre_run: list[Callable[[PipelineContext], PipelineContext]] = field(default_factory=list)
    post_run: list[Callable[[PipelineContext], PipelineContext]] = field(default_factory=list)
    post_report: list[Callable[[PipelineContext], None]] = field(default_factory=list)
```

This is how you get to "another ecosystem" without rewriting — teams write hooks, not forks.

### 3.5 Introduce a Scoring Interface with Confidence Labels

**Current state:** Phase-3-prompt-a asks for simple heuristic scoring with `low/medium/high`.

**Proposed:** A pluggable scoring protocol with the confidence system from Graphify:

```python
class ScoringAdapter(Protocol):
    def score(self, reference: ArtifactRef, candidates: list[ArtifactRef]) -> ScoreResult: ...

@dataclass
class ScoreResult:
    best_match: ArtifactRef
    confidence: Literal["CONFIRMED", "LIKELY", "POSSIBLE", "INCONCLUSIVE"]
    score: float              # 0.0 - 1.0
    method: str               # "structural", "pixel", "ocr", "ml"
    evidence: list[str]       # Human-readable reasons
```

Implementations:
- `StructuralScorer` (MVP — size, aspect ratio, basic comparison)
- `PixelScorer` (Pillow/OpenCV — histogram, SSIM)
- `OCRScorer` (text extraction + comparison)
- `MLScorer` (future — trained classifier)

Each scorer is independent and can be composed.

### 3.6 Add a Security Module

Bug-agent handles:
- **Shell commands** (subprocess with user-provided paths)
- **File paths** (user-provided `--image`, `--app-path`)
- **Credentials** (fixture files with passwords)

There is no centralized validation. Create `security.py`:

```python
def validate_path(path: Path, allowed_root: Path) -> Path:
    """Prevent directory traversal. Resolve and check containment."""

def sanitize_shell_arg(arg: str) -> str:
    """Allowlist characters for shell arguments."""

def redact_secrets(data: dict, secret_fields: set[str]) -> dict:
    """Replace secret values with '[REDACTED]' for logging/reports."""
```

Every module that touches paths, shell, or credentials goes through this.

### 3.7 Token-Efficient AI Integration (When LLM Planning Arrives)

Phase-4-prompt-c introduces `LLMPlanner`. Graphify's core lesson: **don't feed everything to the LLM every time**.

When LLM planning is added:
- Build a **flow graph** once (like Graphify's code graph) — which flows exist, what they test, how they relate
- When the LLM plans, send only the relevant subgraph (flow descriptions matching the bug keywords), not the entire flow library
- Cache LLM planning results keyed by `SHA256(description + platform + flow_library_version)`
- Use structured output (JSON mode) so results are machine-parseable

Expected token reduction: 10-50x per planning query vs. naive "here are all my flows, pick some."

---

## 4. Prompt Pipeline Improvements

### 4.1 Current Problem: Prompts Build Incrementally Without a Contract

The 17 prompts build the system in sequence, but each prompt re-explains context from scratch and there's no shared contract document that all prompts reference. If a developer runs prompt 3-a without having run 1-a through 2-c, the AI has no idea what exists.

**Proposed fix:** Create a `CONTRACTS.md` that every prompt references:

```markdown
# Retracer Contracts

## Pipeline Stages
1. intake → PipelineContext
2. preflight → PipelineContext (with preflight results)
3. plan → PipelineContext (with candidate flows)
4. execute → PipelineContext (with run results)
5. capture → PipelineContext (with artifacts)
6. score → PipelineContext (with confidence labels)
7. report → PipelineContext (with report path)

## Canonical Schemas
- Incident: {...}
- RunResult: {...}
- ScoreResult: {...}
- ArtifactRef: {...}

## Adapter Interfaces
- AutomationAdapter: run_flow(), capture_screenshot(), collect_ui_tree()
- ScoringAdapter: score()
- PlannerAdapter: plan()
- PlatformConfig: simulator_cmd, device_discovery_fn, ...
```

Every prompt gets a preamble: *"Read `docs/CONTRACTS.md` first. Your implementation must conform to these interfaces."*

### 4.2 Missing: A "Doctor" Prompt for the Prompt System Itself

Graphify has `benchmark.py` to prove its own value. Bug-agent should have a meta-prompt that validates the current state:

```
Analyze the current retracer codebase.
Verify that:
- All pipeline stages exist and conform to the contract
- All adapters implement the required interface
- All schemas are consistent across modules
- No platform-specific logic leaks outside platforms/
- Security module covers all shell/path/credential operations
Report gaps as a structured checklist.
```

### 4.3 Prompts Should Be Platform-Parametric

Current prompts hardcode "Maestro", "iOS", "tvOS". For generalization:

Replace:
> "Implement the Maestro runner"

With:
> "Implement the first automation adapter (Maestro for iOS/tvOS). Follow the AutomationAdapter protocol. The same pattern will be used for XCUITest, Appium, and Playwright."

This mindset shift costs nothing but makes every prompt produce more portable code.

---

## 5. Generalization Roadmap

### Phase G1: Internalize the Pipeline (no new features, just restructure)

- [ ] Create `pipeline.py` with `PipelineContext` and explicit stage chain
- [ ] Create `platforms/base.py` with `PlatformConfig` protocol
- [ ] Move iOS/tvOS specifics into `platforms/ios.py` and `platforms/tvos.py`
- [ ] Create `security.py` as the validation boundary
- [ ] Define canonical `RunResult`, `ScoreResult`, `ArtifactRef` schemas
- [ ] Create `docs/CONTRACTS.md`
- [ ] Update all prompts to reference contracts

### Phase G2: Scoring & Caching (improve existing features)

- [ ] Implement pluggable `ScoringAdapter` with confidence labels
- [ ] Add SHA256 content-addressable caching for flow results
- [ ] Add structured scoring output to reports
- [ ] Add graceful degradation (core works without optional deps)

### Phase G3: Second Ecosystem Proof (prove generalization)

- [ ] Add `platforms/android.py` with `PlatformConfig` for Android emulator + adb
- [ ] Add `runners/appium_runner.py` implementing `AutomationAdapter`
- [ ] Run the same pipeline against an Android app
- [ ] Validate that zero core modules changed

### Phase G4: AI-Powered Planning (token-efficient)

- [ ] Build a flow graph / flow index (inspired by Graphify's code graph)
- [ ] Implement `LLMPlanner` with subgraph-based context (not full flow library)
- [ ] Add caching for LLM planning results
- [ ] Add confidence labels to planned flows

---

## 6. Concrete File Structure (After Generalization)

```
retracer/
  __init__.py
  cli.py
  config.py
  pipeline.py                    # NEW: Explicit pipeline chain
  security.py                    # NEW: Centralized validation
  
  models/
    incident.py
    run_result.py                # Canonical RunResult schema
    score_result.py              # NEW: Canonical ScoreResult with confidence
    artifact_ref.py              # NEW: Canonical artifact reference
    pipeline_context.py          # NEW: PipelineContext dataclass
  
  platforms/                     # NEW: Platform configs (Graphify's LanguageConfig pattern)
    base.py                      # PlatformConfig protocol
    ios.py
    tvos.py
    android.py                   # Future
    web.py                       # Future
  
  intake/
    submit.py
    validator.py
  
  planner/
    base.py                      # PlannerAdapter protocol
    rule_planner.py              # Current keyword-based planner
    llm_planner.py               # Future: LLM-based with flow graph
    flow_library.py
  
  runners/
    base.py                      # AutomationAdapter protocol
    maestro_runner.py
    xcuitest_runner.py
    appium_runner.py             # Future
    playwright_runner.py         # Future
  
  environment/                   # Renamed from simulator/ (it's not always a simulator)
    detect.py
    app_state.py
    preflight.py
  
  artifacts/
    store.py
    screenshots.py
    cache.py                     # NEW: SHA256 content-addressable cache
    logs.py
  
  scoring/
    base.py                      # ScoringAdapter protocol
    structural_scorer.py
    pixel_scorer.py              # Future: OpenCV/Pillow
    ocr_scorer.py                # Future: text extraction
  
  reporting/
    markdown_report.py
    bundle.py
    hooks.py                     # NEW: post-report hooks (GitHub, Jira, Slack)
  
  utils/
    fs.py
    shell.py
    timestamps.py
```

---

## 7. Key Takeaways

| Graphify Pattern | Retracer Application | Impact |
|-----------------|----------------------|--------|
| Pure function pipeline | Explicit `PipelineContext` → stage → `PipelineContext` | Any stage swappable, testable in isolation |
| Data-driven configs | `PlatformConfig` dataclass per ecosystem | New platform = new config, not new code |
| Canonical data format | Strict `RunResult`, `ScoreResult`, `ArtifactRef` schemas | Adapters are truly interchangeable |
| Confidence labels | `CONFIRMED/LIKELY/POSSIBLE/INCONCLUSIVE` | Honest scoring, machine-actionable |
| Content-addressable cache | SHA256-keyed flow results and screenshots | Skip redundant re-runs in CI |
| Graceful degradation | Core works without Maestro/OpenCV/LLM | Lower barrier to entry |
| Security boundary | Single `security.py` chokepoint | Auditable, prevents shell injection and path traversal |
| Token efficiency | Flow graph + subgraph extraction for LLM planning | 10-50x cheaper AI queries |
| Hook/plugin system | Pre-run, post-run, post-report hooks | Teams customize without forking |

**The bottom line:** Bug-agent is 80% there. The pipeline shape, the adapter pattern, the phased approach — all good. What's missing is the **explicit contracts, platform abstraction, and the mindset shift from "tool" to "UI bug reproduction framework that happens to use first."** That shift, done now while the codebase is small, costs very little and unlocks everything.

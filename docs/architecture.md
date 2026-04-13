# **Architecture Document**

## **Title**

**Retracer for iOS/tvOS UI Bug Reproduction and Triage**

## **1\. Goal**

Build a separate tool called **retracer** that helps engineers reproduce hard-to-find UI bugs in iOS/tvOS apps.

The first goal is not fully autonomous fixing.

The first goal is:

* accept a screenshot and/or text description  
* run a known app build already opened in simulator by a developer  
* automate candidate UI flows  
* capture screenshots and evidence  
* generate a structured bug report  
* make it easy to extend later into fix generation, regression validation, and real-device support

---

## **2\. MVP Assumptions**

For the MVP:

* the developer manually starts the correct app/build in simulator  
* the tool does **not** install builds yet  
* the tool does **not** use real devices yet  
* the tool does **not** attempt auto-fixing yet  
* the tool does **not** depend on TestFlight APIs  
* the tool runs on a macOS machine with Xcode and simulator available  
* the tool uses **Python for orchestration**  
* the tool uses **Maestro first** for quick black-box UI automation  
* the system is designed so that **XCUITest can be added next**

---

## **3\. Why this order**

This order reduces complexity.

Instead of solving all of these at once:

* build discovery  
* artifact install  
* simulator boot/install  
* UI automation  
* screenshot matching  
* issue reporting  
* root-cause analysis  
* code fixing

we start with the smallest useful loop:

1. app already running in simulator  
2. run retracer against that running app  
3. execute candidate repro flows  
4. collect evidence  
5. produce report

That creates value quickly and gives a base for automation later.

---

## **4\. Core User Flow**

### **Input from developer or QA**

The user provides:

* platform: `ios` or `tvos`  
* bug description  
* optional screenshot  
* optional fixture name  
* optional notes

Example:

retracer submit \
  --platform tvos \
  --description "Profile menu overlays sport home screen" \
  --image ./bug.png \
  --fixture sports_family_account

### **What happens**

The system:

1. validates environment  
2. checks that simulator is booted and app is running  
3. creates an incident manifest  
4. selects candidate repro flows  
5. runs flows through automation  
6. captures screenshots and artifacts  
7. scores whether the bug likely reproduced  
8. generates a structured markdown report  
9. stores results for later review

## **5\. High-Level Architecture**
User / Developer
    |
    v
CLI or Internal UI
    |
    v
Python Orchestrator
    |
    +--> Incident Intake
    +--> Scenario Planner
    +--> Runner Controller
    +--> Artifact Collector
    +--> Similarity/Scoring
    +--> Report Generator
    |
    v
Automation Adapter Layer
    |
    +--> Maestro Adapter (MVP)
    +--> XCUITest Adapter (Phase 2)
    +--> Real Device Adapter (future)
    |
    v
Simulator / Device Execution
    |
    v
Artifacts + Reports + Logs


## **6\. Components**

## **6.1 CLI**

Responsibilities:

* accept user input  
* create incident files  
* start runs  
* view reports

Commands:

* `retracer submit`  
* `retracer run`  
* `retracer report`  
* `retracer doctor`

## **6.2 Incident Intake**

Responsibilities:

* normalize input into JSON  
* validate paths and options  
* assign incident ID  
* store metadata

Example manifest:

{
  "incident_id": "inc_0001",
  "platform": "tvos",
  "description": "Profile menu overlays sport home screen",
  "image_path": "./bug.png",
  "fixture": "sports_family_account",
  "created_at": "2026-04-10T10:00:00Z",
  "status": "submitted"
}

## **6.3 Scenario Planner**

Responsibilities:

* convert description into candidate repro flows  
* pick flows from a reusable flow library  
* support phase-based logic:  
  * fixed flows first  
  * generated flows later

Example candidate flows:

* `launch_to_sport_then_open_profile_menu`  
* `resume_app_then_open_profile_menu`  
* `switch_profile_then_navigate_to_sport`  
* `open_account_then_back_then_profile_menu`

## **6.4 Automation Adapter Layer**

A stable Python interface should hide the underlying automation tool.

Example interface:

class AutomationAdapter(Protocol):
    def run_flow(self, flow_id: str, context: dict) -> "RunResult":
        ...
    def capture_screenshot(self, name: str) -> str:
        ...
    def collect_ui_tree(self) -> dict:
        ...

Adapters:

* `MaestroAdapter`  
* `XCUITestAdapter`  
* future `DeviceAdapter`

---

## **6.5 Maestro Adapter**

MVP runner.

Responsibilities:

* invoke Maestro flows from Python  
* pass environment variables / fixture data  
* collect screenshots  
* collect stdout/stderr  
* save run metadata

Why first:

* quick to author  
* easy for agents to generate  
* enough for broad black-box repro experiments

## **6.6 Artifact Collector**

Collect:

* screenshots  
* optional screen recordings later  
* run logs  
* flow execution metadata  
* similarity results  
* generated report

Folder structure example:

runs/
  inc_0001/
    manifest.json
    run_001/
      screenshots/
      logs/
      result.json
    report.md

## **6.7 Similarity and Scoring**

Initial version should be simple.

Inputs:

* user screenshot  
* screenshots from each run  
* visible text extracted from images or UI metadata  
* flow metadata

Output:

* similarity score  
* likely reproduced: yes/no  
* best matching run/frame  
* notes

Start simple with:

* text overlap  
* image dimension sanity  
* basic structural comparison  
* manual confidence notes

Later add:

* computer vision  
* screen classification  
* modal/overlay detection  
* OCR-driven matching

---

## **6.8 Report Generator**

Generate a markdown report with:

* incident summary  
* input description  
* fixture used  
* flows attempted  
* best matching run  
* screenshots  
* confidence  
* suggested next steps

## **7\. Repository Structure**

retracer/
  README.md
  pyproject.toml
  .gitignore
  retracer/
    __init__.py
    cli.py
    config.py
    models/
      incident.py
      run_result.py
      report.py
    intake/
      submit.py
      validator.py
    planner/
      planner.py
      flow_library.py
    runners/
      base.py
      maestro_runner.py
      xcuitest_runner.py
    simulator/
      detect.py
      app_state.py
    artifacts/
      store.py
      screenshots.py
      logs.py
    scoring/
      similarity.py
    reporting/
      markdown_report.py
    utils/
      fs.py
      shell.py
      timestamps.py
  flows/
    maestro/
      common/
      ios/
      tvos/
  fixtures/
    accounts/
      sports_family_account.json
  runs/
  docs/
    architecture.md
    roadmap.md
    prompts/

## **8\. Phase Plan**

## **Phase 1**

Focus:

* local CLI  
* incident manifest  
* simulator/app detection  
* Maestro integration  
* hardcoded flow execution  
* artifact capture  
* markdown report

## **Phase 2**

Focus:

* planner improvements  
* multiple candidate flows  
* screenshot scoring  
* reusable flow library  
* XCUITest adapter foundation

## **Phase 3**

Focus:

* build resolution and installation automation  
* simulator boot/install/reset  
* fixture management  
* CI integration  
* optional issue creation

## **Phase 4**

Focus:

* codebase-aware bug report enrichment  
* root-cause hints  
* fix proposal pipeline  
* validation reruns  
* PR creation

## **Enhancements**

* real devices  
* tvOS focus-state hooks  
* OCR and vision  
* remote config snapshots  
* Android/web adapters  
* regression packs  
* autonomous fix loops with guardrails

## **9\. Non-Goals for MVP**

Do not attempt in MVP:

* autonomous production debugging  
* direct TestFlight install to simulator  
* auto-merge fixes  
* broad CV magic  
* full root-cause accuracy  
* exact production parity

---

## **10\. Success Criteria for MVP**

The MVP is successful if:

* a developer can point the tool at a running simulator app  
* the tool can run one or more predefined UI flows  
* it captures screenshots and logs  
* it produces a clean markdown report  
* it can be extended without major rewrites

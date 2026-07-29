# SIM-006: Detection Rule Simulator — Team Architecture & Blueprint

## 1. Executive Summary & Core Requirements

As a 4-person team working remotely across different locations, our goal is to build **SIM-006 (Detection Rule Simulator)** from scratch. The simulator evaluates 8 predefined detection rules against synthetic event inputs to trigger gate decisions (PASS, WARN, HARD_FAIL).

### Key Technical & Operational Principles

- **License Compliance:** We are using a 100% safe, open-source stack with permissive licenses (MIT, Apache 2.0, BSD).
- **Stateless & Read-Only Logic:** Evaluation is stateless per call with zero mutation of state. Every output is tagged `"simulated": true`.
- **No Code Duplication:** A single underlying `RuleEngine` powers all three interfaces: CLI, FastAPI, and Streamlit UI.
- **Target Test Coverage:** Minimum ≥70% test coverage using pytest.

---

## 2. Safe Open-Source Tech Stack

We selected these tools to avoid licensing risks and ensure quick setup on all 4 remote devices:

| Layer | Tool / Library | License Type | Purpose |
|---|---|---|---|
| Language | Python 3.10+ | PSF License | Standard programming environment |
| Data Schema | Pydantic v2 | MIT License | Event and request validation |
| API Framework | FastAPI + Uvicorn | MIT License | Auto-generated REST API (`/evaluate`, `/rules`, `/health`) |
| UI Framework | Streamlit | Apache 2.0 | Web dashboard for manual testing and JSON download |
| Testing | pytest + pytest-cov | MIT License | Unit/integration tests and coverage verification |

---

## 3. Team Member Role Segregation & File Ownership

To prevent Git merge conflicts while working remotely, our repository is strictly divided by file ownership:

```
sim_006/
├── models.py          <-- Developer 1
├── engine.py           <-- Developer 1
├── rules.py             <-- Developer 2
├── api.py               <-- Developer 3
├── cli.py                <-- Developer 3
├── streamlit_app.py     <-- Developer 4
└── tests/                <-- Shared (see Section 4.3)
```

### Developer 1: Models & Core Engine
**Files:** `models.py`, `engine.py`

**Tasks:**
- Implement Pydantic v2 models (`Event`, `EvaluationRequest`, `RuleEvaluationResult`, `EvaluationResponse`).
- Build the `RuleEngine` execution loop.
- Implement worst-result-wins gate aggregation logic (HARD_FAIL > WARN > PASS).
- Ensure `"simulated": true` is present on all response objects.

### Developer 2: Detection Rules Registry
**Files:** `rules.py`

**Tasks:**
- Write pure handler functions for all 8 rules (R-01 through R-08).
- Implement threshold checks (Voltage escalation ±10%, Temperature escalation ±10%).
- Map rule IDs to functions inside a dictionary registry (rule_id → handler function).

### Developer 3: API & CLI Interfaces
**Files:** `api.py`, `cli.py`

**Tasks:**
- Build FastAPI endpoints (POST `/evaluate`, GET `/rules`, GET `/health`).
- Build CLI command interface (`python -m sim_006 evaluate` & `list-rules`).
- Ensure both interfaces directly call Dev 1's `RuleEngine`.
- Own the package entry point (`__init__.py`, `__main__.py`) — see Section 4.4.

### Developer 4: Streamlit UI & Integration Testing
**Files:** `streamlit_app.py`, `tests/test_integration.py`

**Tasks:**
- Build Streamlit web dashboard for uploading JSON events and rendering colored gate badges.
- Own integration test suite covering TC-006-04 (multi-rule aggregation).
- Achieve and report ≥70% overall test coverage (final sign-off — see Section 4.3 for full test ownership split).

---

## 4. Interface Contracts (Must Be Agreed Before Coding Starts)

These are the exact contracts between modules that prevent integration breakage at merge time. All 4 developers should read this section before writing any code.

### 4.1 Rule Registry Contract (Dev 1 ↔ Dev 2)

`rules.py` (Dev 2) must export a single object with this exact shape:

```python
RULE_REGISTRY: Dict[str, RuleDefinition]

class RuleDefinition(NamedTuple):
    rule_id: str                 # e.g. "R-01"
    rule_name: str               # e.g. "Replay attack detected"
    handler: Callable[[Event], RuleEvaluationResult]
    description: str             # for GET /rules
```

`engine.py` (Dev 1) imports `RULE_REGISTRY` and never hardcodes rule logic — it only orchestrates. If a rule needs to be added or changed, only `rules.py` changes; `engine.py` never does.

**Decision needed today:** Dev 1 and Dev 2 confirm this exact signature in a 5-minute call before either starts, so both sides build to the same contract.

### 4.2 Statelessness Exception — R-01 and R-08

The blueprint states evaluation is "stateless per call with zero mutation of state." R-01 (replay detection) and R-08 (impossible telemetry) both require knowledge of a *prior* event to function — a single event can't be self-evidently a replay or a physically-impossible jump.

**Resolution:** Statelessness is preserved by requiring the **caller** to supply prior-state fields inside the event payload itself. The engine still holds no memory between calls.

Add these fields to the `Event` model (Dev 1, `models.py`) if not already present:

```python
last_seen_sequence_number: Optional[int] = None
last_seen_timestamp: Optional[datetime] = None
prior_soc_percent: Optional[float] = None
charging_source_present: Optional[bool] = None
```

- **R-01** compares `sequence_number` against `last_seen_sequence_number`, and `timestamp` against `last_seen_timestamp` + an acceptable staleness window.
- **R-08** compares `soc_percent` against `prior_soc_percent`; if the increase exceeds the defined threshold (e.g. >5%) and `charging_source_present == False`, it's a HARD_FAIL.

If no prior-state fields are supplied, R-01 and R-08 should **default to PASS with a `detail` note explaining insufficient data to evaluate** — not silently skip, and not fail closed on missing context (this is the one exception to the general fail-safe principle, because failing closed here would flag every first-ever event as suspicious).

**Owner:** Dev 2 implements this logic; Dev 1 ensures the model fields exist. Confirm together before Dev 2 starts `rules.py`.

### 4.3 Test Ownership (Revised)

Original plan had Dev 4 owning 100% of `tests/`, which creates a bottleneck and prevents Dev 1/Dev 2 from verifying their own work in isolation. Revised split:

| Owner | Test file | Scope |
|---|---|---|
| Dev 1 | `tests/test_models.py`, `tests/test_engine.py` | Model validation, gate aggregation logic |
| Dev 2 | `tests/test_rules.py` | All 8 rules individually (TC-006-01, 02, 03, 05) |
| Dev 3 | `tests/test_api.py`, `tests/test_cli.py` | Endpoint and CLI behavior |
| Dev 4 | `tests/test_integration.py` | Multi-rule aggregation (TC-006-04), coverage reporting, final ≥70% verification |

Each dev writes tests for their own module as they build it, not after. Dev 4's role shifts from "writes all tests" to "owns integration testing + final coverage sign-off."

### 4.4 Package Entry Point

`sim_006/__init__.py` and `sim_006/__main__.py` wire the CLI entry point (`python -m sim_006`).

**Owner:** Developer 3 (already owns `cli.py`, the natural home for this).

---

## 5. Git & Remote Workflow

Standard workflow for all 4 developers, enforced consistently regardless of location:

1. Write assigned code in your owned sub-module (per Section 3 file ownership).
2. Run unit tests locally (`pytest`).
3. Confirm tests pass and coverage ≥70% for your module before proceeding.
4. Commit and push changes to your feature branch.
5. Open a Pull Request to `main`.
6. A teammate reviews the code and approves.
7. Merge into `main` branch.
8. All remote team members pull the updated `main`.

No direct commits to `main` — every change goes through PR review, even for small fixes, since all 4 developers are working from different files that ultimately depend on each other's contracts (Section 4).

---

*iTelematics Software Pvt Ltd | Battery Cybersecurity Platform | SIM-006*

# SIM-006 — Production Build Spec (Final Addendum)

**Purpose of this document:** This resolves every remaining ambiguity in the PRD and Team Blueprint. It is the last document needed before coding starts. Read this alongside `SIM-006_Detection_Rule_Simulator_PRD.md` and `SIM-006_Team_Blueprint_v2.md`.

**Build mode:** One AI agent builds the entire module end-to-end, sequentially, following the phase order in the PRD's Section 16. The "Developer 1–4" roles in the Blueprint are treated as **logical build phases**, not separate humans — build them in that order (Models/Engine → Rules → API/CLI → Streamlit/Tests) so each phase can be tested before the next depends on it.

---

## 1. Resolved Numeric Constants

Do not invent these — use exactly these values.

### R-01: Replay Attack Detection
- **Staleness window:** an event's `timestamp` is considered stale if it is **more than 30 seconds older** than the current evaluation time, OR older than the paired `last_seen_timestamp`.
- **Duplicate sequence:** `sequence_number == last_seen_sequence_number` → immediate HARD_FAIL, regardless of timestamp.
- Define as a named constant: `REPLAY_STALENESS_WINDOW_SECONDS = 30`

### R-05: Voltage Range (48V pack)
- **Safe range:** 40V – 56V → PASS
- **WARN range:** outside 40–56V but within ±10% of the boundary → WARN
  - i.e. 36V ≤ voltage < 40V, or 56V < voltage ≤ 61.6V
- **HARD_FAIL range:** beyond ±10% of the boundary
  - i.e. voltage < 36V, or voltage > 61.6V
- Define as named constants: `VOLTAGE_SAFE_MIN = 40.0`, `VOLTAGE_SAFE_MAX = 56.0`, `VOLTAGE_ESCALATION_PCT = 0.10`

### R-06: Critical Temperature
- **Safe range:** -20°C – 55°C → PASS
- **WARN range:** outside that range but within ±10% of the boundary
  - i.e. -22°C ≤ temp < -20°C, or 55°C < temp ≤ 60.5°C
- **HARD_FAIL range:** beyond ±10% of the boundary
  - i.e. temp < -22°C, or temp > 60.5°C
- Define as named constants: `TEMP_SAFE_MIN = -20.0`, `TEMP_SAFE_MAX = 55.0`, `TEMP_ESCALATION_PCT = 0.10`

### R-08: Impossible Telemetry
- **SOC jump threshold:** `soc_percent - prior_soc_percent > 5.0` (percentage points) while `charging_source_present == False` → HARD_FAIL
- Define as named constant: `SOC_JUMP_THRESHOLD_PCT = 5.0`

**All constants live in one place:** `sim_006/constants.py`, imported by `rules.py`. Never hardcode these numbers inline inside rule functions.

---

## 2. Timezone Convention

- All timestamps are **UTC, ISO 8601 format** (e.g. `2026-07-29T14:30:00Z`).
- Pydantic `datetime` fields must be **timezone-aware**. Reject naive datetimes at the schema level — do not silently assume UTC on unlabeled input.
- "Current evaluation time" for staleness checks (R-01) uses `datetime.now(timezone.utc)` at the moment `RuleEngine.evaluate()` runs.

---

## 3. Missing-Context Handling (R-01 / R-08)

Per the Blueprint's Section 4.2: if `last_seen_sequence_number`, `last_seen_timestamp`, or `prior_soc_percent` are `None`, the rule returns:

```json
{
  "rule_id": "R-01",
  "rule_name": "Replay attack detected",
  "result": "PASS",
  "detail": "Insufficient prior-state context to evaluate — treated as first-seen event"
}
```

This exact `detail` wording (or equivalent) should be used consistently so test assertions can match on it predictably.

---

## 4. Error Handling Contract

### Invalid `rule_id` in request
- If any `rule_id` in the request doesn't exist in `RULE_REGISTRY`, return **HTTP 400** with:
```json
{
  "error": "unknown_rule_id",
  "detail": "Rule ID 'R-99' not found. Valid rule IDs: R-01, R-02, ..., R-08",
  "simulated": true
}
```

### Malformed event payload
- Pydantic validation failures return FastAPI's default **HTTP 422** response — do not override this, it's already structured and standard.

### CLI errors
- Same logic, but printed to stderr and exits with non-zero status code. No stack traces shown to the user — catch and format cleanly.

---

## 5. Coding Standards

- **Type hints are mandatory** on every function signature, no exceptions.
- **Docstrings:** Google style, required on every public function/class (rule handlers, `RuleEngine` methods, API route handlers).
- **Formatter:** `black` (line length 100)
- **Linter:** `ruff`
- **Import order:** stdlib → third-party → local, enforced by `ruff` isort rules
- No bare `except:` — always catch specific exceptions
- No mutable default arguments

---

## 6. Environment & Bootstrap

```bash
# Create and activate virtual environment
python3.10 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

**`requirements.txt`** (pinned versions — agent should verify latest patch versions at build time but stay within these major/minor versions):

```
fastapi>=0.110,<0.120
uvicorn[standard]>=0.29,<0.35
pydantic>=2.6,<3.0
streamlit>=1.32,<1.40
pytest>=8.0,<9.0
pytest-cov>=5.0,<6.0
ruff>=0.4,<1.0
black>=24.0,<25.0
```

**`.gitignore`** must include: `venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.coverage`, `htmlcov/`, `.env`

---

## 7. Required Test Fixtures (Use These Exact Payloads)

Place in `tests/fixtures/` as individual JSON files, referenced by all test files so everyone's tests use identical data.

**`fixtures/event_missing_timestamp.json`** (TC-006-01)
```json
{
  "battery_id": "BID-001",
  "event": {
    "event_type": "telemetry",
    "timestamp": null,
    "voltage_v": 48.2,
    "temperature_c": 28.1,
    "soc_percent": 78.3,
    "sequence_number": 1001
  },
  "rule_ids": ["R-02"]
}
```
**Expected:** R-02 → HARD_FAIL

**`fixtures/event_voltage_warn.json`** (TC-006-02)
```json
{
  "battery_id": "BID-002",
  "event": {
    "event_type": "telemetry",
    "timestamp": "2026-07-29T14:30:00Z",
    "voltage_v": 58.0,
    "temperature_c": 25.0,
    "soc_percent": 60.0,
    "sequence_number": 2001
  },
  "rule_ids": ["R-05"]
}
```
**Expected:** R-05 → WARN (58.0V is between 56 and 61.6)

**`fixtures/event_all_pass.json`** (TC-006-03)
```json
{
  "battery_id": "BID-003",
  "event": {
    "event_type": "telemetry",
    "timestamp": "2026-07-29T14:30:00Z",
    "voltage_v": 48.0,
    "temperature_c": 25.0,
    "soc_percent": 60.0,
    "sequence_number": 3001,
    "certificate_expiry": "2027-01-01T00:00:00Z",
    "firmware_hash": "abc123",
    "expected_firmware_hash": "abc123",
    "open_incident": false,
    "prior_soc_percent": 58.0,
    "charging_source_present": true,
    "last_seen_sequence_number": 3000,
    "last_seen_timestamp": "2026-07-29T14:29:50Z"
  },
  "rule_ids": "all"
}
```
**Expected:** all 8 rules → PASS, `overall_gate: PASS`

**`fixtures/event_mixed_result.json`** (TC-006-04)
```json
{
  "battery_id": "BID-004",
  "event": {
    "event_type": "telemetry",
    "timestamp": null,
    "voltage_v": 58.0,
    "temperature_c": 25.0,
    "soc_percent": 60.0,
    "sequence_number": 4001
  },
  "rule_ids": ["R-02", "R-05", "R-06"]
}
```
**Expected:** R-02 → HARD_FAIL, R-05 → WARN, R-06 → PASS, `overall_gate: HARD_FAIL` (worst result wins)

**`fixtures/event_impossible_soc.json`** (TC-006-05)
```json
{
  "battery_id": "BID-005",
  "event": {
    "event_type": "telemetry",
    "timestamp": "2026-07-29T14:30:00Z",
    "voltage_v": 48.0,
    "temperature_c": 25.0,
    "soc_percent": 70.0,
    "sequence_number": 5001,
    "prior_soc_percent": 60.0,
    "charging_source_present": false
  },
  "rule_ids": ["R-08"]
}
```
**Expected:** R-08 → HARD_FAIL (10-point SOC jump with no charging source)

---

## 8. CI Enforcement (GitHub Actions)

**`.github/workflows/test.yml`**
```yaml
name: Test Suite

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      - name: Lint
        run: |
          ruff check .
          black --check .
      - name: Run tests with coverage
        run: |
          pytest --cov=sim_006 --cov-report=term-missing --cov-fail-under=70
```

This blocks any PR from merging if coverage drops below 70% or lint fails — enforces the Blueprint's Section 5 workflow automatically instead of relying on manual discipline.

---

## 9. Final Pre-Flight Checklist

Before telling the agent "go," confirm these three documents are all provided together as context:
1. `SIM-006_Detection_Rule_Simulator_PRD.md` — the "what" (models, rules, requirements)
2. `SIM-006_Team_Blueprint_v2.md` — the "how it's organized" (architecture, contracts)
3. This document — the "exact numbers and setup" (constants, fixtures, environment, CI)

With all three, the agent has zero remaining decisions to invent — every threshold, fixture, error format, and setup step is specified.

---

*iTelematics Software Pvt Ltd | Battery Cybersecurity Platform | SIM-006*

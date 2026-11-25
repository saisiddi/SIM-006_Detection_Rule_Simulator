# SIM-006 — Detection Rule Simulator

Part of the **Battery Cybersecurity Platform** (iTelematics Software Pvt Ltd).
Simulates 8 predefined detection rules against synthetic battery events and
produces pass / warning / hard-fail gate decisions.

> Every output this system produces is tagged `"simulated": true`.
> No real security events or incident data are used anywhere.

---

## What it does

Consumes synthetic events (telemetry, identity, firmware, cyber) produced by
generators such as SIM-002 / SIM-003 / SIM-005, evaluates selected detection
rules, and aggregates a worst-result-wins gate decision:
`HARD_FAIL > WARN > PASS`.

## The 8 detection rules

| Rule | Name | Trigger | Result |
|---|---|---|---|
| R-01 | Replay attack detected | Timestamp >30s older than evaluation time or `last_seen_timestamp`, or `sequence_number` duplicates `last_seen_sequence_number` | HARD_FAIL |
| R-02 | Missing telemetry timestamp | `timestamp` is null on a telemetry event | HARD_FAIL |
| R-03 | Invalid or expired certificate | `certificate_expiry` in the past, or certificate missing on an identity event | HARD_FAIL |
| R-04 | Firmware hash mismatch | `firmware_hash != expected_firmware_hash`, or hashes missing on a firmware event | HARD_FAIL |
| R-05 | Voltage out of range | Safe: 40–56V. WARN within +/-10% of a boundary (36–40V, 56–61.6V) | HARD_FAIL beyond |
| R-06 | Critical temperature | Safe: -20–55C. WARN within +/-10% of a boundary (-22 to -20C, 55–60.5C) | HARD_FAIL beyond |
| R-07 | Open cyber incident linked to battery | `open_incident == true` | HARD_FAIL |
| R-08 | Physically impossible telemetry | `soc_percent` jumps >5 points over `prior_soc_percent` without a charging source (false or unknown) | HARD_FAIL |

Additional behavior:

- A telemetry event missing a measurement it should carry
  (`voltage_v`, `temperature_c`, `open_incident`, `soc_percent`) yields WARN
  on the corresponding rule — missing measurements are suspicious, not neutral.
- R-01 / R-08 return PASS with an explicit "insufficient prior-state context"
  note when the caller supplies no prior-state fields (they are stateless;
  prior state travels inside the event payload).
- Bypass: evaluating a subset of rules excludes the rest from the gate
  decision. The bypass is logged (WARNING level) — never silent.

## Setup

Requires Python 3.10+ (built and tested on 3.12).

```bash
python3.10 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium   # only needed for scripts/take_screenshots.py
```

## Usage

### CLI

```bash
python -m sim_006 evaluate --event samples/evaluate_input.json --rules R-02,R-05,R-06
python -m sim_006 evaluate --event samples/evaluate_input.json --rules all
python -m sim_006 list-rules
python -m sim_006 explain --event samples/evaluate_input.json
```

The `--event` file holds a full evaluation request
(`{battery_id, event, rule_ids?}`); `--rules` overrides the file's `rule_ids`
and is required only if the file omits them. Responses print as JSON on
stdout; errors print to stderr with a non-zero exit code.

### API

```bash
uvicorn sim_006.api:app --port 8000
```

| Method | Path | Description |
|---|---|---|
| POST | `/evaluate` | Evaluate rules against an event |
| POST | `/explain` | Explain an existing deterministic evaluation |
| GET | `/rules` | Rule catalogue with descriptions and thresholds |
| GET | `/health` | Health check |

Interactive OpenAPI docs: `http://localhost:8000/docs`.

`/explain` accepts `{"evaluation": <response from /evaluate>}`. It does not
re-run or alter detection. With no provider configured, it returns a structured
deterministic fallback and marks `ai_generated: false`.

```bash
curl -X POST http://localhost:8000/evaluate \
  -H "Content-Type: application/json" \
  -d @samples/evaluate_input.json
```

Errors: unknown or empty rule selection -> HTTP 400 (`unknown_rule_id` /
`empty_rule_selection` payload, tagged `simulated: true`); malformed payloads
-> FastAPI's standard HTTP 422.

### Streamlit UI

```bash
streamlit run sim_006/streamlit_app.py
```

Paste or upload a request JSON, multi-select rules or evaluate all,
click **Run Evaluation**, review the color-coded gate badge
(green PASS / yellow WARN / red HARD_FAIL) and results table, and download
the JSON report.

The **Test Event Simulator** section provides ten valid local profiles,
editable JSON, validation, direct evaluation, and a fallback explanation.

### Input simulator

The local harness in `sim_006.simulator` models the current `Event` contract.
It does not claim to reproduce undocumented upstream schemas. Profiles are:
normal, replay, missing timestamp, invalid certificate, firmware mismatch,
unsafe voltage, critical temperature, cyber incident, impossible SOC change,
and multi-condition. Each profile returns a validated `EvaluationRequest`:

```python
from sim_006.engine import RuleEngine
from sim_006.simulator import generate_request

response = RuleEngine().evaluate(generate_request("unsafe_voltage"))
assert response.overall_gate == "HARD_FAIL"
```

### Explanation and security boundary

The deterministic `RuleEngine` is always authoritative. The explanation
adapter receives only an existing `EvaluationResponse`; it cannot change event
data, create detections, suppress rules, or change the gate. Provider output is
validated and the gate is restored from the original response. No external AI
dependency or API key is required, and no provider is configured by default.
Event text is data, not instructions, and the application does not execute
event or explanation content.

### Sample input / output

`samples/evaluate_input.json` -> `samples/evaluate_output.json` matches
PRD Section 11 exactly.

## Testing

```bash
pytest                          # full suite
pytest --cov=sim_006 --cov-report=term-missing --cov-fail-under=70
ruff check .
black --check .
```

Current status: 192 tests passing, 95.30% statement coverage
(see `evidence/coverage.txt`).

## Evidence package

| Item | Location |
|---|---|
| UI screenshots (PASS / HARD_FAIL) | `evidence/ui_pass.png`, `evidence/ui_hard_fail.png` |
| Coverage report | `evidence/coverage.txt` |
| Stress & validation report | `evidence/final_stress_test_report.md` |
| Phase 10 sign-off checklist | `evidence/phase10_signoff.md` |
| Sample input/output (PRD Section 11) | `samples/` |
| Test fixtures (Build Spec Section 7) | `tests/fixtures/` |
| Architecture document | `docs/architecture.md` |
| Threat model note (WP-005-S1) | `docs/threat_model.md` |

## Project layout

```
sim_006/
  __init__.py        # package exports
  __main__.py        # python -m sim_006 entry point
  constants.py       # every numeric threshold (never hardcoded elsewhere)
  models.py          # Pydantic v2 models
  rules.py           # R-01..R-08 handlers + RULE_REGISTRY
  engine.py          # RuleEngine orchestration + gate aggregation
  simulator.py       # Reusable local upstream-event profiles
  explanation.py      # Structured explanation provider boundary + fallback
  cli.py             # CLI interface
  api.py             # FastAPI interface
  streamlit_app.py   # Streamlit UI
scripts/take_screenshots.py  # UI evidence generation (Playwright)
tests/               # pytest suite (fixtures/, per-module tests, integration)
```

## License

Internal project — iTelematics Software Pvt Ltd.

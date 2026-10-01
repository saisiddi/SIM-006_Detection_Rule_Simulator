# SIM-006 — Architecture Document

Expands PRD Section 9 with the implementation decisions made during the build.
All decisions were either taken directly from the PRD / Team Blueprint /
Production Build Spec, or confirmed with the product owner during the build.

## 1. Data flow

```
Event (JSON request: {battery_id, event, rule_ids})
     |
     v
 Schema validation (Pydantic v2, fail fast — naive datetimes rejected)
     |
     v
 RuleEngine.evaluate(request)
     |
     |-- resolves rule_ids ("all" or subset; empty/unknown -> error)
     |-- runs RULE_REGISTRY[rule_id].handler(event) per selected rule
     |
     v
 List[RuleEvaluationResult]
     |
     v
 Gate Aggregator: overall_gate = worst result (HARD_FAIL > WARN > PASS)
     |
     v
 EvaluationResponse (JSON, simulated=true always)

For local testing, `sim_006.simulator.generate_request()` supplies validated
synthetic upstream profiles before this same flow. After evaluation, the
optional `/explain` endpoint passes the existing response to
`ExplanationService`; it never sends raw event data to a decision-making
engine and never changes the gate.
```

Three interfaces — CLI (`sim_006/cli.py`), FastAPI (`sim_006/api.py`),
Streamlit (`sim_006/streamlit_app.py`) — all delegate to this single
`RuleEngine`. No rule logic exists in any interface layer; integration tests
prove all three return byte-identical responses for identical requests.

## 2. Module responsibilities and ownership (Team Blueprint v2)

| Module | Owner (logical phase) | Responsibility |
|---|---|---|
| `models.py` | Dev 1 | Pydantic v2 models; timezone-aware datetime enforcement |
| `engine.py` | Dev 1 | Orchestration, gate aggregation, rule-selection errors |
| `rules.py` | Dev 2 | 8 pure rule handlers + RULE_REGISTRY |
| `api.py` | Dev 3 | FastAPI endpoints, error-to-HTTP mapping |
| `cli.py` | Dev 3 | CLI + `__main__.py` entry point |
| `streamlit_app.py` | Dev 4 | Streamlit dashboard |
| `simulator.py` | test harness | Reusable validated upstream-event profiles |
| `explanation.py` | explanation layer | Structured provider boundary and deterministic fallback |
| `scripts/` | tooling | Screenshot evidence generation |
| `tests/` | shared (Blueprint 4.3 split) | models / rules / engine / api+cli / integration / UI |

## 3. Key contracts

### 3.1 Rule registry (Blueprint 4.1)

```python
RULE_REGISTRY: dict[str, RuleDefinition]
RuleDefinition = NamedTuple(rule_id, rule_name, handler, description)
# handler: (Event) -> RuleEvaluationResult — pure, read-only
```

The engine never hardcodes rule logic; adding a 9th rule touches only
`rules.py`. Verified by the registry completeness test.

### 3.2 Statelessness (Blueprint 4.2)

The engine holds no memory between calls. R-01 / R-08 read prior state from
caller-supplied event fields (`last_seen_sequence_number`,
`last_seen_timestamp`, `prior_soc_percent`, `charging_source_present`).
When these are absent, R-01 / R-08 return PASS with the exact detail
"Insufficient prior-state context to evaluate — treated as first-seen event"
(Build Spec 3). `Event` is frozen (immutable); a purity test proves handlers
never mutate it.

### 3.3 Constants

Every numeric threshold lives in `sim_006/constants.py`
(`REPLAY_STALENESS_WINDOW_SECONDS`, `VOLTAGE_SAFE_MIN/MAX`,
`VOLTAGE_ESCALATION_PCT`, `TEMP_SAFE_MIN/MAX`, `TEMP_ESCALATION_PCT`,
`SOC_JUMP_THRESHOLD_PCT`) and is imported by `rules.py`. WARN bands are
computed from the escalation percentages, never restated inline.

## 4. Implementation decisions and their sources

| Decision | Source / ruling |
|---|---|
| Evaluation clock: `datetime.now(timezone.utc)` read at evaluation time; wrapped in `_utcnow()` so tests freeze it deterministically | Build Spec 2 (timezone convention) |
| Timestamps must be timezone-aware; naive datetimes rejected at schema level | Build Spec 2 |
| `Event` frozen; engine/read-only, no shared-state writes | PRD 7 / 13 |
| Missing `certificate_expiry` (R-03) / firmware hashes (R-04) are HARD_FAIL only on identity / firmware events respectively; expired certs and mismatched hashes fail closed on any event type | PRD 6 trigger wording, conservative reading |
| Missing measurements on telemetry events (`voltage_v`, `temperature_c`, `open_incident`) -> WARN, not PASS; non-telemetry events pass with an explicit "not applicable" detail | Product-owner ruling (Correction 2, Phase 3) |
| R-08: missing `soc_percent` on telemetry -> WARN; computed jump >5 points with `charging_source_present` unknown -> HARD_FAIL (closing the None-is-not-False gap) | Product-owner ruling (Phase 3) |
| Engine signature: `evaluate(request: EvaluationRequest) -> EvaluationResponse` | Product-owner ruling (Phase 4) |
| Bypass = subset selection; excluded rules logged at WARNING level outside `gate_reason`, so PRD 11 output matches exactly while logging stays non-silent | Product-owner ruling (Phase 5) |
| `gate_reason` wording: Section 11 exact form for single triggers ("Rule R-02 triggered HARD_FAIL"), "Rules R-01, R-02 triggered HARD_FAIL" for multiple, "All N rules passed" for clean runs | Product-owner ruling (Phase 4) |
| Empty `rule_ids` list rejected (`empty_rule_selection`, HTTP 400 / CLI exit 1) — evaluating nothing must never silently gate PASS | Product-owner ruling (Phase 4) |
| Error contract: `unknown_rule_id` / `empty_rule_selection` -> HTTP 400 with Build Spec 4 payload; malformed payloads -> FastAPI default 422 (not overridden); CLI mirrors on stderr without stack traces | Build Spec 4 |
| `/rules` response = `{"rules": [{rule_id, rule_name, description}], "simulated": true}` — thresholds embedded in each description | PRD 10.2 + mandatory simulated tag |
| httpx (FastAPI TestClient) and playwright (UI screenshot evidence) added to requirements.txt beyond the Build Spec list | Product-owner approvals (Phases 6 and 7) |
| Venv on Python 3.12 (machine default 3.14 cannot build Pillow pinned by streamlit<1.40) | Phase 1 constraint, PRD floor 3.10+ |

## 5. Security posture

- Synthetic data only; no real security events anywhere in the codebase.
- All response objects carry `"simulated": true`.
- Input validated before evaluation (fail fast, no silent coercion of
  genuinely wrong types).
- Fail-closed bias on positive detections (expired certificates, hash
  mismatches, unknown charging source); fail-open only for the documented
  first-seen prior-state exception of R-01 / R-08.
- Explanation providers receive an existing `EvaluationResponse` only.
  Provider output is schema-validated, the original gate is authoritative,
  and malformed output falls back locally. No provider, secret, tool access,
  or code execution is enabled by default.

## 6. Testing and CI

- 136 pytest tests across models, rules, engine, API, CLI, integration, and
  UI layers, using the 5 exact Build Spec 7 fixtures.
- Statement coverage: 100% (target >=70%; `evidence/coverage.txt`).
- GitHub Actions (`/.github/workflows/test.yml`): ruff, black --check, and
  `pytest --cov=sim_006 --cov-fail-under=70` on Python 3.10, blocking merges
  that regress either lint or coverage (Build Spec 8).

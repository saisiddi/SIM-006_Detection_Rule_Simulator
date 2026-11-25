# SIM-006 — Final Stress & Validation Report

Generated: 2026-10-01T11:53:04.518778+00:00 — independent adversarial
pass, separate from the 192-test pytest suite (95.30% statement coverage). 10,000 synthetic events,
live uvicorn server, concurrent clients (16 threads).

## Section summary

| # | Section | Result |
|---|---|---|
| 1 | Volume/perf (10,000 events x 3 interfaces) | PASS |
| 2 | Concurrency/statelessness (64 mixed-gate requests) | PASS |
| 3 | Boundary/edge fuzzing (33 cases) | PASS |
| 4 | Cross-interface parity (30 requests) | PASS |
| 5 | Adversarial/security (7 probes) | PASS |
| 6 | Full regression (pytest+lint) | PASS |

## 1. Volume / performance — 10,000 events per interface

| Interface | Total time (s) | Avg latency (ms/eval) | Errors |
|---|---|---|---|
| Engine (direct, in-process) | 0.11 | 0.011 | 0 |
| API (HTTP, concurrent, 16 threads) | 5.90 | 0.590 | 0 |
| CLI (in-process batch) | 4.56 | 0.456 | 0 |

CLI latency includes JSON parsing, model validation, and (suppressed) pretty-print
per call; API latency includes full HTTP round-trips to a local uvicorn server.
CLI per-eval latency is inflated by the batch harness itself: one bypass warning
line written to stderr per subset request (a real CLI invocation is one process
per request and logs once); engine latency is the pure rule-evaluation cost.

## 2. Concurrency / statelessness

64 simultaneous requests with distinct battery_ids and
deliberately mixed expected gates (PASS / WARN / HARD_FAIL), 16 threads:
cross-contaminated responses: **0**;
wrong-gate responses: **0**;
HTTP errors: **0**. No response contained another
request's data.

## 3. Boundary / edge fuzzing

33 cases: both edges of both severity bands (R-05, R-06), the 30s R-01
staleness edge and the 30s future-skew edge, last_seen_timestamp ordering, the
5.0-point SOC jump edge, plus extremes (negative voltage, absolute-zero
temperature, SOC=150 which is now rejected at schema validation, 2^63 and
negative sequence numbers, year-2000 and year-2126 timestamps — the latter now
flagged by R-01). Failures: none. No unhandled exceptions anywhere.

## 4. Cross-interface parity

30 varied generated requests (beyond the 5 mandated fixtures).
All 30 responses semantically identical (same EvaluationResponse document) across engine, API, and CLI.

## 5. Adversarial / security

| Probe | Outcome |
|---|---|
| unknown extra event fields -> HTTP 422 (extra='forbid') | as expected |
| wrong-typed voltage -> HTTP 422 | as expected |
| deeply nested extra JSON handled without crash | as expected |
| oversized 5MB string -> HTTP 422 | as expected |
| naive datetime -> HTTP 422 | as expected |
| event_type spoof handled deterministically | as expected |
| simulated:true on every non-422 response path | as expected |

## 6. Full regression

- pytest --cov=sim_006 --cov-fail-under=70: exit 0 (192 passed, 1 warning in 2.46s)
- ruff check .: exit 0
- black --check .: exit 0

## Findings — disposition after Phase 10 hardening

Status is re-derived from live behaviour on every run of this script;
nothing below is asserted from memory.

| # | Finding (original wording) | Status | Reasoning |
|---|---|---|---|
| 1 | schema has no 0-100 bound on soc_percent (PRD 5.1 defines types only) | **Resolved** | Event.soc_percent and prior_soc_percent now carry inclusive 0-100 bounds from SOC_MIN_PCT/SOC_MAX_PCT; this run confirmed a 150% reading is rejected at schema validation before R-08 executes. |
| 2 | far-future timestamps are not flagged: R-01 staleness is defined one-way (older only) in Build Spec 1 — potential spec gap | **Resolved** | R-01 now flags timestamps more than REPLAY_MAX_FUTURE_SKEW_SECONDS (30s, symmetric with the staleness window) ahead of the evaluation clock; this run confirmed a year-2126 timestamp returns HARD_FAIL. |
| 3 | unknown extra event fields are silently ignored (Pydantic default extra='ignore'); PRD 7 says reject malformed input — extra='forbid' may be intended but is nowhere specified | **Resolved** | Event now sets extra='forbid'; this run confirmed an unknown key is rejected with HTTP 422 before any rule runs. All 5 Build Spec 7 fixtures re-verified unaffected. |
| 4 | 5MB string field accepted (no length limits in models; spec silent — potential DoS surface at the API boundary) | **Resolved** | firmware_hash/expected_firmware_hash capped at FIRMWARE_HASH_MAX_LENGTH (128) and battery_id at BATTERY_ID_MAX_LENGTH (64); this run confirmed a 5MB value is rejected with HTTP 422 before any rule runs. |
| 5 | event_type spoofing: telemetry-shaped data labeled 'identity' bypasses R-02/R-05/R-06/R-07 — by design (event_type is assigned by trusted generators), but worth a Threat Model note (WP-005-S1) | **Resolved — documented** | Written up as docs/threat_model.md for WP-005-S1: rule-coverage table, residual-risk rating, and the recommended ingress control that binds event_type to the authenticated producer identity. Behaviour is unchanged — it is a trust boundary, not a rule defect. |
| 6 | simulated-tag audit: 200/400 bodies, /rules, /health, and CLI stdout all carry simulated=true; FastAPI's default 422 body does not (explicitly kept per Build Spec 4); CLI schema-error stderr text is plain text | **Rejected — intentional** | Build Spec Section 4 defines the 422 body and the CLI schema-error stderr text verbatim and does not tag them; leaving them untagged is a deliberate contract decision, now stated explicitly in docs/architecture.md Section 5 rather than left implicit. |

### New observations from this run

- None.

## Verdict

**READY for Phase 10 sign-off — all 6 sections PASS and all 6 carried-over findings are Resolved or explicitly Rejected with reasoning; see the disposition table below.**

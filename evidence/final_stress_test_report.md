# SIM-006 — Final Stress & Validation Report

Generated: 2026-07-29T13:39:53.092295+00:00 — independent adversarial
pass, separate from the 136-test pytest suite. 10,000 synthetic events,
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
| Engine (direct, in-process) | 0.20 | 0.020 | 0 |
| API (HTTP, concurrent, 16 threads) | 35.82 | 3.582 | 0 |
| CLI (in-process batch) | 258.17 | 25.817 | 0 |

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
staleness edge, last_seen_timestamp ordering, the 5.0-point SOC jump edge, plus
extremes (negative voltage, absolute-zero temperature, SOC=150, 2^63 and negative
sequence numbers, year-2000 and year-2126 timestamps). Failures: none.
No unhandled exceptions anywhere.

## 4. Cross-interface parity

30 varied generated requests (beyond the 5 mandated fixtures).
All 30 responses semantically identical (same EvaluationResponse document) across engine, API, and CLI.

## 5. Adversarial / security

| Probe | Outcome |
|---|---|
| unknown extra fields: accepted but documented (no crash) | as expected |
| wrong-typed voltage -> HTTP 422 | as expected |
| deeply nested extra JSON handled without crash | as expected |
| oversized 5MB field handled without crash | as expected |
| naive datetime -> HTTP 422 | as expected |
| event_type spoof handled deterministically | as expected |
| simulated:true on every non-422 response path | as expected |

## 6. Full regression

- pytest --cov=sim_006 --cov-fail-under=70: exit 0 (136 passed in 13.38s)
- ruff check .: exit 0
- black --check .: exit 0

## Findings (spec gaps / observations — no crashes, no defects)

- boundary observation — schema has no 0-100 bound on soc_percent (PRD 5.1 defines types only)
- boundary observation — far-future timestamps are not flagged: R-01 staleness is defined one-way (older only) in Build Spec 1 — potential spec gap
- unknown extra event fields are silently ignored (Pydantic default extra='ignore'); PRD 7 says reject malformed input — extra='forbid' may be intended but is nowhere specified
- 5MB string field accepted (no length limits in models; spec silent — potential DoS surface at the API boundary)
- event_type spoofing: telemetry-shaped data labeled 'identity' bypasses R-02/R-05/R-06/R-07 — by design (event_type is assigned by trusted generators), but worth a Threat Model note (WP-005-S1)
- simulated-tag audit: 200/400 bodies, /rules, /health, and CLI stdout all carry simulated=true; FastAPI's default 422 body does not (explicitly kept per Build Spec 4); CLI schema-error stderr text is plain text

## Verdict

**READY for Phase 10 sign-off — no defects found; listed findings are documented spec gaps/observations, none require code changes unless you decide otherwise.**

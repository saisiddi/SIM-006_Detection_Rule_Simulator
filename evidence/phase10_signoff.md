# SIM-006 — Phase 10 Sign-off

**Date:** 2026-10-01
**Base:** `b666c82` (main, PR #4 merged)
**Branch:** `feat/dev-006-phase10-hardening`
**Scope:** PRD Section 14 (deliverables) + Section 15 (Definition of Done), re-verified
against this branch.

Every row below was checked by running the command shown, not by recalling an
earlier run. Re-run them from the repo root to reproduce.

```bash
python -m pytest -q --cov=sim_006 --cov-report=term-missing --cov-fail-under=70
ruff check .
black --check .
python scripts/final_stress_test.py
python scripts/take_screenshots.py
```

---

## 1. PRD Section 14 — Required Deliverables / Evidence Checklist

| # | Deliverable | Status | Evidence / how it was verified |
|---|---|---|---|
| 1 | Source code (`sim_006`: models, rule registry, rule engine, CLI, API, Streamlit app) | PASS | `sim_006/{models,rules,engine,cli,api,streamlit_app,constants,explanation,simulator}.py` — 9 modules, all present |
| 2 | `README.md` (setup, usage for CLI/API/UI, examples) | PASS | `README.md` — Sections 1–6 cover setup, CLI, API, UI, evidence; test/coverage claims corrected this phase (was stale "136 tests / 100%") |
| 3 | API documentation, accessible | PASS | FastAPI `/docs` (Swagger) and `/redoc`; static snapshot at `openapi.json`. Verified by hitting `/docs` → HTTP 200 during this phase |
| 4 | Architecture document (PRD Section 9 expanded with implementation decisions) | PASS | `docs/architecture.md` — Sections 1–6 including the Section 4 implementation-decisions table with the source PRD/Build-Spec reference for each decision |
| 5 | Test suite (`pytest`) covering all cases in Section 12 | PASS | **192 tests.** All five required IDs present: `grep -rho "TC-006-[0-9]*" tests/ \| sort -u` → `TC-006-01 … TC-006-05`. Also-required cases present: rule bypass/exclusion (`test_engine.py`, `test_cli.py`), `list-rules` completeness (`test_cli.py`, `test_api.py`), schema-validation rejection (`test_models.py`, `test_api.py`, `test_streamlit_app.py`) |
| 6 | Coverage report (≥70%) | PASS | **95.30%** (532 statements, 25 missed) — `evidence/coverage.txt`; gate enforced in CI at `--cov-fail-under=70` |
| 7 | Sample input/output matching Section 11 | PASS | `samples/evaluate_input.json` is byte-equivalent to the PRD Section 11 input. Re-evaluated through the live engine this phase: output **exactly equals** `samples/evaluate_output.json` (`True`) — all 3 results, `overall_gate`, `gate_reason`, `simulated` |
| 8 | Screenshots of Streamlit UI in action (PASS and HARD_FAIL) | PASS | `evidence/ui_pass.png`, `evidence/ui_hard_fail.png` — regenerated this phase via `scripts/take_screenshots.py` against the hardened build |
| 9 | `git` repo with clean history, feature branch, PR ready for review | PASS | Single feature branch `feat/dev-006-phase10-hardening` off `b666c82`; working tree clean before commit; PR opened for review (this document is part of it) |

## 2. PRD Section 15 — Definition of Done

| # | DoD item | Status | Evidence / how it was verified |
|---|---|---|---|
| 1 | All 8 rules implemented with correct logic and thresholds | PASS | `RULE_REGISTRY` → `len == 8`, keys `R-01 … R-08`; every threshold read from `sim_006/constants.py` (no inlined literals) — `docs/architecture.md` Section 3.3 |
| 2 | Gate decision (PASS/WARN/HARD_FAIL) by "worst result wins" | PASS | `sim_006/engine.py` ranking `HARD_FAIL > WARN > PASS`; covered by `tests/test_engine.py` incl. TC-006-04 (one HARD_FAIL overrides a WARN) |
| 3 | `pytest` passing with ≥70% coverage | PASS | **192 passed, 0 failed, 95.30%** on this branch; `ruff check .` clean, `black --check .` clean (24 files) |
| 4 | Streamlit and FastAPI both working and calling the same underlying engine | PASS | Both import `RuleEngine` from `sim_006.engine` (`api.py:52`, `streamlit_app.py:319`); UI boots and `/health`,`/rules`,`/evaluate`,`/docs` all HTTP 200; stress Section 4 cross-interface parity: **30/30 responses semantically identical** across engine, API, and CLI |
| 5 | README and evidence package complete | PASS | `evidence/`: `coverage.txt`, `final_stress_test_report.md`, `ui_pass.png`, `ui_hard_fail.png`, `phase10_signoff.md`; plus `docs/architecture.md`, `docs/threat_model.md`, `samples/`, `tests/fixtures/` |

## 3. Independent stress & validation pass

`evidence/final_stress_test_report.md`, regenerated on this branch by
`python scripts/final_stress_test.py`:

| Section | Result |
|---|---|
| 1 Volume/perf (10,000 events × 3 interfaces) | PASS |
| 2 Concurrency/statelessness (64 mixed-gate requests) | PASS |
| 3 Boundary/edge fuzzing (33 cases) | PASS |
| 4 Cross-interface parity (30 requests) | PASS |
| 5 Adversarial/security (7 probes) | PASS |
| 6 Full regression (pytest + ruff + black) | PASS |

**Verdict: READY for Phase 10 sign-off** — all 6 sections PASS and all 6
carried-over findings are Resolved or explicitly Rejected with reasoning.
Status in that report is re-derived from live behaviour on every run, so the
claim cannot go stale unnoticed.

## 4. Deviations register (PRD Section 0 — deviations must be flagged)

Four product-owner-approved schema/rule fixes deliberately deviate from the
PRD/Build Spec as written. Full reasoning in `docs/architecture.md` Section 4.

| # | Deviation | From | Justification |
|---|---|---|---|
| 1 | `soc_percent` / `prior_soc_percent` bounded to inclusive 0–100 | PRD 5.1 (types only) | Physical bound; a 150% reading is now rejected at schema validation rather than reaching R-08 |
| 2 | R-01 also flags timestamps >30s **ahead** of evaluation time (`REPLAY_MAX_FUTURE_SKEW_SECONDS = 30`) | Build Spec 1 (staleness defined one-way) | Window chosen symmetric with the existing `REPLAY_STALENESS_WINDOW_SECONDS = 30`; approved in concept |
| 3 | `Event` uses `extra="forbid"` | PRD 5.1 (default `extra="ignore"`) | PRD 7 requires rejecting malformed input; all 5 Build Spec Section 7 fixtures verified unaffected |
| 4 | String length caps: `battery_id` ≤64, `firmware_hash` / `expected_firmware_hash` ≤128 | PRD 5.1 (silent) | Closes the 5 MB-string payload surface at the API boundary. **Note:** no string-typed certificate field exists — `certificate_expiry` is a `datetime`, so there is nothing to cap there |

Related non-schema notes:

- **`event_type` spoofing** (finding 5) is a trust-boundary property, not a
  defect — documented for **WP-005-S1** in `docs/threat_model.md`.
- **Untagged 422 body / CLI schema-error stderr** (finding 6) is an
  intentional Build Spec Section 4 contract decision, now stated explicitly in
  `docs/architecture.md` Section 5 rather than left implicit.
- **Test-only change:** `tests/test_streamlit_app.py` now freezes
  `simulator._now` alongside `rules._utcnow`. Required because R-01 became
  symmetric — a generated wall-clock event would otherwise be skewed against a
  frozen evaluation clock and legitimately fail as a future timestamp. The
  assertion under test (`Overall gate: PASS`) is unchanged.

## 5. Out of scope and untouched

`sim_006/explanation.py` and `sim_006/simulator.py` **logic** were not modified
in this phase (unreviewed PR #3 work). No logic change was required for any of
the four fixes; if one had been, work would have stopped for instruction.

---

## 6. CI

See the checks on the pull request that contains this file: `.github/workflows/test.yml`
runs `ruff check .`, `black --check .`, and
`pytest --cov=sim_006 --cov-fail-under=70` on Python 3.10.

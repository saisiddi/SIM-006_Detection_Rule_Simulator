# SIM-006 — Threat Model Note

**Reference:** WP-005-S1 (Threat Model), which uses the SIM-006 rule catalogue as
reference material.

**Status:** informational note produced by the Phase 10 review. It records an
existing trust boundary; it does not change any rule's behavior.

All input here is synthetic. No real security events or incident data are used
anywhere in this system.

---

## 1. Scope

This note covers the trust boundary around `Event.event_type`, which the
`event_type`-spoofing observation in `evidence/final_stress_test_report.md`
flagged for a WP-005-S1 reference.

## 2. The trust boundary

`event_type` is one of `telemetry | identity | firmware | cyber`. It is the
**only** field that selects which detection rules apply to an event:

| `event_type` | Rules that can fire | Rules that pass as "not applicable" |
|---|---|---|
| `telemetry` | R-01, R-02, R-05, R-06, R-07, R-08 | R-03, R-04 |
| `identity` | R-01, R-03, R-07 | R-02, R-04, R-05, R-06, R-08 |
| `firmware` | R-01, R-04, R-07 | R-02, R-03, R-05, R-06, R-08 |
| `cyber` | R-01, R-07 | R-02, R-03, R-04, R-05, R-06, R-08 |

**SIM-006 trusts the caller's `event_type`.** It is not authenticated,
signed, or cross-checked against the shape of the payload. The engine treats it
as an assertion of the event's origin, not as a claim to be verified.

## 3. Spoofing scenario

A telemetry-shaped payload — one carrying `voltage_v`, `temperature_c`,
`open_incident`, `soc_percent` — can be labelled `"identity"`.

Consequence: **R-02, R-05, R-06 and R-07 pass as "not applicable"** for that
event, so out-of-range voltage, critical temperature, a null timestamp, or an
open cyber incident would not be raised by their telemetry rules. R-03 would
instead evaluate the event as an identity event (and HARD_FAIL if no valid
certificate is present), so the gate is not left wide open — but the
measurement rules are silently skipped.

This is **by design**, not a defect:

- `event_type` is assigned by the trusted upstream generators in this platform
  (SIM-002 / SIM-003 / SIM-005), which is the boundary where the label is
  actually decided.
- Inferring `event_type` from payload shape inside SIM-006 would be guesswork
  and would contradict the PRD, which defines `event_type` as an explicit
  field (Section 5.1).

## 4. Residual risk and recommended control

| Item | Assessment |
|---|---|
| Severity | Medium — depends entirely on whether a caller can supply arbitrary events |
| Exploitable in this repo | No. All inputs are synthetic and local; there is no untrusted producer wired in |
| Exploitable at integration (SIM-010) | **Yes**, if an untrusted or compromised upstream can POST events directly |
| Recommended control (owner: WP-005-S1) | Bind `event_type` to the authenticated producer identity at the platform ingress, before SIM-006 sees the event. SIM-006 should remain schema-validated but origin-trusting. |
| Fallback control | If ingress binding is unavailable, validate payload shape against the declared `event_type` at the gateway and reject mismatches rather than re-labelling them. |

## 5. Related notes

- **Fail-closed bias.** Positive detections fail closed (expired certificates,
  hash mismatches, unknown charging source). The only documented fail-open
  cases are the R-01 / R-08 "insufficient prior-state context" first-seen
  exception.
- **Schema hardening (Phase 10).** Unknown fields are rejected
  (`extra="forbid"`), `soc_percent` is bounded to 0-100, and string fields are
  length-capped. These close the payload-shape surface but do **not** address
  `event_type` origin, which remains an ingress responsibility.
- **422 responses carry no `simulated` tag** — intentional, see
  `docs/architecture.md` Section 5 (Security posture).

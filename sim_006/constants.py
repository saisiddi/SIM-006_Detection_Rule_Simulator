"""Named constants for SIM-006 detection rules.

All numeric thresholds resolved in the Production Build Spec (Section 1) live
here and are imported by :mod:`sim_006.rules`. Never hardcode these values
inline inside rule functions.
"""

REPLAY_STALENESS_WINDOW_SECONDS: int = 30

# R-01 future-skew window. Symmetric with REPLAY_STALENESS_WINDOW_SECONDS:
# a timestamp more than this far AHEAD of the evaluation clock is flagged
# the same way a stale one is (product-owner approved, Phase 10 hardening).
REPLAY_MAX_FUTURE_SKEW_SECONDS: int = 30

# Physical bounds for state-of-charge readings (percent).
SOC_MIN_PCT: float = 0.0
SOC_MAX_PCT: float = 100.0

# String length caps at the schema boundary (DoS / payload-size surface).
BATTERY_ID_MAX_LENGTH: int = 64
FIRMWARE_HASH_MAX_LENGTH: int = 128

VOLTAGE_SAFE_MIN: float = 40.0
VOLTAGE_SAFE_MAX: float = 56.0
VOLTAGE_ESCALATION_PCT: float = 0.10

TEMP_SAFE_MIN: float = -20.0
TEMP_SAFE_MAX: float = 55.0
TEMP_ESCALATION_PCT: float = 0.10

SOC_JUMP_THRESHOLD_PCT: float = 5.0

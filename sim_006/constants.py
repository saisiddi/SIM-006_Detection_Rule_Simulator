"""Named constants for SIM-006 detection rules.

All numeric thresholds resolved in the Production Build Spec (Section 1) live
here and are imported by :mod:`sim_006.rules`. Never hardcode these values
inline inside rule functions.
"""

REPLAY_STALENESS_WINDOW_SECONDS: int = 30

VOLTAGE_SAFE_MIN: float = 40.0
VOLTAGE_SAFE_MAX: float = 56.0
VOLTAGE_ESCALATION_PCT: float = 0.10

TEMP_SAFE_MIN: float = -20.0
TEMP_SAFE_MAX: float = 55.0
TEMP_ESCALATION_PCT: float = 0.10

SOC_JUMP_THRESHOLD_PCT: float = 5.0

"""Synthetic upstream event profiles for local SIM-006 testing."""

from datetime import datetime, timedelta, timezone
from typing import Literal

from sim_006.models import EvaluationRequest, Event

Scenario = Literal[
    "normal", "replay", "missing_timestamp", "invalid_certificate",
    "firmware_mismatch", "unsafe_voltage", "critical_temperature",
    "cyber_incident", "impossible_soc", "multi_condition",
]

SCENARIOS: tuple[Scenario, ...] = (
    "normal", "replay", "missing_timestamp", "invalid_certificate",
    "firmware_mismatch", "unsafe_voltage", "critical_temperature",
    "cyber_incident", "impossible_soc", "multi_condition",
)

SCENARIO_LABELS = {
    "normal": "Normal telemetry", "replay": "Replay attack",
    "missing_timestamp": "Missing timestamp", "invalid_certificate": "Invalid certificate",
    "firmware_mismatch": "Firmware mismatch", "unsafe_voltage": "Unsafe voltage",
    "critical_temperature": "Critical temperature", "cyber_incident": "Open cyber incident",
    "impossible_soc": "Impossible SOC change", "multi_condition": "Multiple conditions",
}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def generate_request(
    scenario: Scenario = "normal",
    *,
    source: Literal["telemetry", "identity", "firmware", "cyber"] = "telemetry",
    battery_id: str = "SIM-BATTERY-001",
) -> EvaluationRequest:
    """Generate a valid request accepted directly by :class:`RuleEngine`.

    Profiles model the fields in the local Event contract; they are a test
    harness, not a claim about an upstream simulator schema.
    """
    timestamp = _now()
    event_data: dict[str, object] = {
        "event_type": source, "timestamp": timestamp, "voltage_v": 48.0,
        "temperature_c": 25.0, "soc_percent": 50.0, "sequence_number": 101,
        "open_incident": False, "prior_soc_percent": 49.0,
        "charging_source_present": True,
    }
    if scenario == "replay":
        event_data.update(sequence_number=100, last_seen_sequence_number=100)
    elif scenario == "missing_timestamp":
        event_data.pop("timestamp")
    elif scenario == "invalid_certificate":
        event_data.update(event_type="identity", certificate_expiry=timestamp - timedelta(days=1))
    elif scenario == "firmware_mismatch":
        event_data.update(event_type="firmware", firmware_hash="observed-hash", expected_firmware_hash="expected-hash")
    elif scenario == "unsafe_voltage":
        event_data["voltage_v"] = 65.0
    elif scenario == "critical_temperature":
        event_data["temperature_c"] = 65.0
    elif scenario == "cyber_incident":
        event_data.update(event_type="cyber", open_incident=True)
    elif scenario == "impossible_soc":
        event_data.update(soc_percent=80.0, prior_soc_percent=50.0, charging_source_present=False)
    elif scenario == "multi_condition":
        event_data.update(voltage_v=65.0, temperature_c=65.0, open_incident=True)
    return EvaluationRequest(battery_id=battery_id, event=Event.model_validate(event_data), rule_ids="all")


def generate_event(scenario: Scenario = "normal", **kwargs: object) -> Event:
    """Generate only the Event portion for callers that already build requests."""
    return generate_request(scenario, **kwargs).event  # type: ignore[arg-type]
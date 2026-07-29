"""Unit tests for the SIM-006 Pydantic models (PRD Section 5)."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from sim_006.models import (
    EvaluationRequest,
    EvaluationResponse,
    Event,
    RuleEvaluationResult,
)

AWARE_TS = "2026-07-29T14:30:00Z"
NAIVE_TS = datetime(2026, 7, 29, 14, 30, 0)


def test_valid_telemetry_event_parses() -> None:
    """A fully populated valid event parses without error."""
    event = Event(
        event_type="telemetry",
        timestamp=datetime(2026, 7, 29, 14, 30, tzinfo=timezone.utc),
        voltage_v=48.2,
        temperature_c=28.1,
        soc_percent=78.3,
        sequence_number=1001,
        prior_soc_percent=77.0,
        charging_source_present=True,
        last_seen_sequence_number=1000,
        last_seen_timestamp=datetime(2026, 7, 29, 14, 29, 55, tzinfo=timezone.utc),
    )
    assert event.event_type == "telemetry"
    assert event.voltage_v == 48.2


def test_event_parses_from_json_fixture_shape() -> None:
    """An event decoded from JSON (ISO string timestamps) parses correctly."""
    event = Event.model_validate(
        {"event_type": "telemetry", "timestamp": AWARE_TS, "voltage_v": 58.0}
    )
    assert event.timestamp is not None
    assert event.timestamp.tzinfo is not None


def test_missing_event_type_rejected() -> None:
    """An event without event_type fails validation."""
    with pytest.raises(ValidationError):
        Event.model_validate({"voltage_v": 48.2})


def test_invalid_event_type_rejected() -> None:
    """An unknown event_type literal fails validation."""
    with pytest.raises(ValidationError):
        Event.model_validate({"event_type": "telemetryy"})


def test_wrong_field_type_rejected() -> None:
    """A non-numeric voltage fails validation."""
    with pytest.raises(ValidationError):
        Event.model_validate({"event_type": "telemetry", "voltage_v": "high"})


@pytest.mark.parametrize("field", ["timestamp", "certificate_expiry", "last_seen_timestamp"])
def test_naive_datetime_rejected(field: str) -> None:
    """Naive (timezone-less) datetimes are rejected per Build Spec Section 2."""
    with pytest.raises(ValidationError):
        Event.model_validate({"event_type": "telemetry", field: NAIVE_TS})


@pytest.mark.parametrize("field", ["timestamp", "certificate_expiry", "last_seen_timestamp"])
def test_timezone_aware_datetime_accepted(field: str) -> None:
    """Timezone-aware datetimes are accepted for all datetime fields."""
    event = Event.model_validate(
        {"event_type": "identity", field: datetime(2027, 1, 1, tzinfo=timezone.utc)}
    )
    assert getattr(event, field) is not None


def test_event_defaults_are_none() -> None:
    """Only event_type is required; every other field defaults to None."""
    event = Event(event_type="cyber")
    assert event.timestamp is None
    assert event.open_incident is None
    assert event.last_seen_sequence_number is None


def test_event_is_read_only() -> None:
    """Event instances are frozen (read-only, PRD Section 13)."""
    event = Event(event_type="telemetry")
    with pytest.raises(ValidationError):
        event.voltage_v = 99.0


def test_evaluation_request_with_rule_list() -> None:
    """EvaluationRequest accepts an explicit list of rule IDs."""
    request = EvaluationRequest(
        battery_id="BID-001",
        event=Event(event_type="telemetry"),
        rule_ids=["R-01", "R-02"],
    )
    assert request.rule_ids == ["R-01", "R-02"]


def test_evaluation_request_with_all() -> None:
    """EvaluationRequest accepts the literal 'all'."""
    request = EvaluationRequest(
        battery_id="BID-001", event=Event(event_type="telemetry"), rule_ids="all"
    )
    assert request.rule_ids == "all"


def test_rule_evaluation_result_validates_result_literal() -> None:
    """RuleEvaluationResult rejects results outside PASS/WARN/HARD_FAIL."""
    with pytest.raises(ValidationError):
        RuleEvaluationResult(
            rule_id="R-01", rule_name="Replay attack detected", result="MAYBE", detail="x"
        )


def test_evaluation_response_defaults_simulated_true() -> None:
    """EvaluationResponse always carries simulated=True by default."""
    response = EvaluationResponse(
        battery_id="BID-001",
        rules_evaluated=1,
        results=[
            RuleEvaluationResult(
                rule_id="R-02",
                rule_name="Missing telemetry timestamp",
                result="PASS",
                detail="timestamp present",
            )
        ],
        overall_gate="PASS",
        gate_reason="All rules passed",
    )
    assert response.simulated is True

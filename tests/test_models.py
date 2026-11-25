"""Unit tests for the SIM-006 Pydantic models (PRD Section 5)."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from sim_006.constants import BATTERY_ID_MAX_LENGTH, FIRMWARE_HASH_MAX_LENGTH
from sim_006.models import (
    EvaluationRequest,
    EvaluationResponse,
    Event,
    RuleEvaluationResult,
)
from tests.conftest import load_fixture

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


# --- Phase 10 hardening: schema-boundary fixes (product-owner approved) ---


@pytest.mark.parametrize(
    "fixture_name",
    [
        "event_all_pass.json",
        "event_impossible_soc.json",
        "event_missing_timestamp.json",
        "event_mixed_result.json",
        "event_voltage_warn.json",
    ],
)
def test_build_spec_fixtures_still_validate_under_extra_forbid(fixture_name: str) -> None:
    """All 5 Build Spec Section 7 fixtures still parse with extra='forbid'."""
    request = EvaluationRequest.model_validate(load_fixture(fixture_name))
    assert request.battery_id
    assert request.rule_ids


def test_unknown_event_field_is_rejected() -> None:
    """extra='forbid' rejects unknown keys instead of silently dropping them (PRD 7)."""
    with pytest.raises(ValidationError) as exc_info:
        Event.model_validate({"event_type": "telemetry", "surprise_field": 1})
    assert "surprise_field" in str(exc_info.value)


def test_known_event_fields_still_accepted() -> None:
    """extra='forbid' does not reject any documented Event field."""
    event = Event.model_validate(load_fixture("event_all_pass.json")["event"])
    assert event.event_type == "telemetry"


@pytest.mark.parametrize("soc", [0.0, 100.0, 50.0, 78.3])
def test_soc_percent_within_bounds_accepted(soc: float) -> None:
    """soc_percent accepts the full inclusive 0-100 range."""
    assert Event.model_validate({"event_type": "telemetry", "soc_percent": soc}).soc_percent == soc


@pytest.mark.parametrize("soc", [-0.1, -1.0, 100.1, 150.0, 200.0])
def test_soc_percent_out_of_bounds_rejected(soc: float) -> None:
    """soc_percent outside 0-100 is rejected at schema validation."""
    with pytest.raises(ValidationError):
        Event.model_validate({"event_type": "telemetry", "soc_percent": soc})


@pytest.mark.parametrize("prior", [0.0, 100.0])
def test_prior_soc_percent_bounds_applied(prior: float) -> None:
    """prior_soc_percent carries the same 0-100 bound as soc_percent."""
    event = Event.model_validate(
        {"event_type": "telemetry", "soc_percent": 50.0, "prior_soc_percent": prior}
    )
    assert event.prior_soc_percent == prior


@pytest.mark.parametrize("prior", [-5.0, 101.0])
def test_prior_soc_percent_out_of_bounds_rejected(prior: float) -> None:
    """prior_soc_percent outside 0-100 is rejected at schema validation."""
    with pytest.raises(ValidationError):
        Event.model_validate(
            {"event_type": "telemetry", "soc_percent": 50.0, "prior_soc_percent": prior}
        )


def test_battery_id_at_max_length_accepted() -> None:
    """battery_id exactly at the cap is accepted."""
    payload = load_fixture("event_all_pass.json")
    payload["battery_id"] = "B" * BATTERY_ID_MAX_LENGTH
    request = EvaluationRequest.model_validate(payload)
    assert len(request.battery_id) == BATTERY_ID_MAX_LENGTH


def test_battery_id_over_max_length_rejected() -> None:
    """battery_id one character over the cap is rejected."""
    payload = load_fixture("event_all_pass.json")
    payload["battery_id"] = "B" * (BATTERY_ID_MAX_LENGTH + 1)
    with pytest.raises(ValidationError):
        EvaluationRequest.model_validate(payload)


def test_firmware_hash_at_max_length_accepted() -> None:
    """firmware_hash exactly at the cap is accepted."""
    event = Event.model_validate(
        {
            "event_type": "firmware",
            "firmware_hash": "a" * FIRMWARE_HASH_MAX_LENGTH,
            "expected_firmware_hash": "b" * FIRMWARE_HASH_MAX_LENGTH,
        }
    )
    assert len(event.firmware_hash or "") == FIRMWARE_HASH_MAX_LENGTH


def test_firmware_hash_over_max_length_rejected() -> None:
    """firmware_hash one character over the cap is rejected."""
    with pytest.raises(ValidationError):
        Event.model_validate(
            {
                "event_type": "firmware",
                "firmware_hash": "a" * (FIRMWARE_HASH_MAX_LENGTH + 1),
            }
        )


def test_megabyte_scale_string_rejected_at_schema_boundary() -> None:
    """The 5MB-string DoS surface is closed: oversized values never reach the rules."""
    with pytest.raises(ValidationError):
        Event.model_validate({"event_type": "firmware", "firmware_hash": "a" * 5_000_000})

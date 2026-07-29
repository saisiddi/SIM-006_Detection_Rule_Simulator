"""Unit tests for the 8 detection rule handlers (PRD Sections 6 and 12)."""

from datetime import datetime, timezone

import pytest

import sim_006.rules as rules
from sim_006.models import Event
from sim_006.rules import INSUFFICIENT_CONTEXT_DETAIL, RULE_REGISTRY
from tests.conftest import load_fixture

FIXED_NOW = datetime(2026, 7, 29, 14, 30, 5, tzinfo=timezone.utc)
_REAL_UTCNOW = rules._utcnow


@pytest.fixture(autouse=True)
def _freeze_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Freeze the evaluation clock so staleness checks are deterministic.

    Calls the real clock first so its code path stays exercised.
    """

    def _frozen() -> datetime:
        _REAL_UTCNOW()
        return FIXED_NOW

    monkeypatch.setattr(rules, "_utcnow", _frozen)


def _event(**overrides: object) -> Event:
    """Build a minimal valid event with per-test overrides.

    Args:
        overrides: Event fields to set.

    Returns:
        A constructed Event.
    """
    return Event.model_validate({"event_type": "telemetry", **overrides})


def test_registry_contains_all_eight_rules() -> None:
    """RULE_REGISTRY holds exactly R-01 through R-08 with matching metadata."""
    assert list(RULE_REGISTRY) == [f"R-{i:02d}" for i in range(1, 9)]
    for rule_id, definition in RULE_REGISTRY.items():
        assert definition.rule_id == rule_id
        assert definition.rule_name
        assert callable(definition.handler)
        assert definition.description


class TestR01:
    """R-01: Replay attack detected."""

    def test_duplicate_sequence_hard_fail(self) -> None:
        result = RULE_REGISTRY["R-01"].handler(
            _event(
                timestamp="2026-07-29T14:30:00Z",
                sequence_number=1001,
                last_seen_sequence_number=1001,
            )
        )
        assert result.result == "HARD_FAIL"
        assert "sequence" in result.detail

    def test_stale_timestamp_vs_evaluation_time_hard_fail(self) -> None:
        result = RULE_REGISTRY["R-01"].handler(
            _event(timestamp="2026-07-29T14:29:00Z", sequence_number=2)
        )
        assert result.result == "HARD_FAIL"
        assert "stale" in result.detail

    def test_timestamp_older_than_last_seen_hard_fail(self) -> None:
        result = RULE_REGISTRY["R-01"].handler(
            _event(
                timestamp="2026-07-29T14:29:55Z",
                last_seen_timestamp="2026-07-29T14:29:58Z",
            )
        )
        assert result.result == "HARD_FAIL"
        assert "last seen" in result.detail

    def test_fresh_event_passes(self) -> None:
        result = RULE_REGISTRY["R-01"].handler(
            _event(
                timestamp="2026-07-29T14:30:00Z",
                sequence_number=3001,
                last_seen_sequence_number=3000,
                last_seen_timestamp="2026-07-29T14:29:50Z",
            )
        )
        assert result.result == "PASS"

    def test_missing_context_passes_with_note(self) -> None:
        result = RULE_REGISTRY["R-01"].handler(_event(sequence_number=1001))
        assert result.result == "PASS"
        assert result.detail == INSUFFICIENT_CONTEXT_DETAIL


class TestR02:
    """R-02: Missing telemetry timestamp (TC-006-01)."""

    def test_tc_006_01_missing_timestamp_hard_fail(self) -> None:
        fixture = load_fixture("event_missing_timestamp.json")
        result = RULE_REGISTRY["R-02"].handler(Event.model_validate(fixture["event"]))
        assert result.rule_id == "R-02"
        assert result.result == "HARD_FAIL"
        assert result.detail == "timestamp field is null"

    def test_present_timestamp_passes(self) -> None:
        result = RULE_REGISTRY["R-02"].handler(_event(timestamp="2026-07-29T14:30:00Z"))
        assert result.result == "PASS"

    def test_non_telemetry_null_timestamp_passes(self) -> None:
        result = RULE_REGISTRY["R-02"].handler(Event(event_type="identity"))
        assert result.result == "PASS"


class TestR03:
    """R-03: Invalid or expired certificate."""

    def test_expired_certificate_hard_fail(self) -> None:
        result = RULE_REGISTRY["R-03"].handler(
            Event(event_type="identity", certificate_expiry="2026-07-29T14:29:00Z")
        )
        assert result.result == "HARD_FAIL"
        assert "past" in result.detail

    def test_missing_certificate_on_identity_hard_fail(self) -> None:
        result = RULE_REGISTRY["R-03"].handler(Event(event_type="identity"))
        assert result.result == "HARD_FAIL"
        assert "missing" in result.detail

    def test_valid_certificate_passes(self) -> None:
        result = RULE_REGISTRY["R-03"].handler(
            Event(event_type="identity", certificate_expiry="2027-01-01T00:00:00Z")
        )
        assert result.result == "PASS"

    def test_missing_certificate_on_telemetry_passes(self) -> None:
        result = RULE_REGISTRY["R-03"].handler(_event())
        assert result.result == "PASS"


class TestR04:
    """R-04: Firmware hash mismatch."""

    def test_mismatch_hard_fail(self) -> None:
        result = RULE_REGISTRY["R-04"].handler(
            Event(
                event_type="firmware",
                firmware_hash="abc123",
                expected_firmware_hash="def456",
            )
        )
        assert result.result == "HARD_FAIL"
        assert "does not match" in result.detail

    def test_missing_hash_on_firmware_event_hard_fail(self) -> None:
        result = RULE_REGISTRY["R-04"].handler(Event(event_type="firmware"))
        assert result.result == "HARD_FAIL"

    def test_matching_hashes_pass(self) -> None:
        result = RULE_REGISTRY["R-04"].handler(
            Event(
                event_type="firmware",
                firmware_hash="abc123",
                expected_firmware_hash="abc123",
            )
        )
        assert result.result == "PASS"

    def test_missing_hashes_on_telemetry_pass(self) -> None:
        result = RULE_REGISTRY["R-04"].handler(_event())
        assert result.result == "PASS"


class TestR05:
    """R-05: Voltage out of range (TC-006-02)."""

    def test_tc_006_02_voltage_58_warn(self) -> None:
        fixture = load_fixture("event_voltage_warn.json")
        result = RULE_REGISTRY["R-05"].handler(Event.model_validate(fixture["event"]))
        assert result.rule_id == "R-05"
        assert result.result == "WARN"

    def test_safe_voltage_passes_with_prd_detail(self) -> None:
        result = RULE_REGISTRY["R-05"].handler(_event(voltage_v=48.2))
        assert result.result == "PASS"
        assert result.detail == "Voltage 48.2V within 40-56V range"

    @pytest.mark.parametrize("voltage", [35.9, 61.7, 0.0, 100.0])
    def test_beyond_escalation_band_hard_fail(self, voltage: float) -> None:
        result = RULE_REGISTRY["R-05"].handler(_event(voltage_v=voltage))
        assert result.result == "HARD_FAIL"

    @pytest.mark.parametrize("voltage", [36.0, 39.9, 56.1, 61.6])
    def test_within_escalation_band_warn(self, voltage: float) -> None:
        result = RULE_REGISTRY["R-05"].handler(_event(voltage_v=voltage))
        assert result.result == "WARN"

    @pytest.mark.parametrize("voltage", [40.0, 56.0])
    def test_boundary_values_pass(self, voltage: float) -> None:
        result = RULE_REGISTRY["R-05"].handler(_event(voltage_v=voltage))
        assert result.result == "PASS"

    def test_missing_voltage_on_telemetry_warns(self) -> None:
        result = RULE_REGISTRY["R-05"].handler(_event())
        assert result.result == "WARN"
        assert "missing" in result.detail

    def test_missing_voltage_on_identity_passes_not_applicable(self) -> None:
        result = RULE_REGISTRY["R-05"].handler(Event(event_type="identity"))
        assert result.result == "PASS"
        assert "not applicable" in result.detail


class TestR06:
    """R-06: Critical temperature."""

    def test_safe_temperature_passes_with_prd_detail(self) -> None:
        result = RULE_REGISTRY["R-06"].handler(_event(temperature_c=28.1))
        assert result.result == "PASS"
        assert result.detail == "Temperature 28.1C within -20-55C range"

    @pytest.mark.parametrize("temperature", [55.1, 60.5, -20.1, -22.0])
    def test_within_escalation_band_warn(self, temperature: float) -> None:
        result = RULE_REGISTRY["R-06"].handler(_event(temperature_c=temperature))
        assert result.result == "WARN"

    @pytest.mark.parametrize("temperature", [60.6, -22.1, 100.0])
    def test_beyond_escalation_band_hard_fail(self, temperature: float) -> None:
        result = RULE_REGISTRY["R-06"].handler(_event(temperature_c=temperature))
        assert result.result == "HARD_FAIL"

    @pytest.mark.parametrize("temperature", [-20.0, 55.0])
    def test_boundary_values_pass(self, temperature: float) -> None:
        result = RULE_REGISTRY["R-06"].handler(_event(temperature_c=temperature))
        assert result.result == "PASS"

    def test_missing_temperature_on_telemetry_warns(self) -> None:
        result = RULE_REGISTRY["R-06"].handler(_event())
        assert result.result == "WARN"
        assert "missing" in result.detail

    def test_missing_temperature_on_identity_passes_not_applicable(self) -> None:
        result = RULE_REGISTRY["R-06"].handler(Event(event_type="identity"))
        assert result.result == "PASS"
        assert "not applicable" in result.detail


class TestR07:
    """R-07: Open cyber incident linked to battery."""

    def test_open_incident_hard_fail(self) -> None:
        result = RULE_REGISTRY["R-07"].handler(_event(open_incident=True))
        assert result.result == "HARD_FAIL"

    def test_no_open_incident_passes(self) -> None:
        result = RULE_REGISTRY["R-07"].handler(_event(open_incident=False))
        assert result.result == "PASS"

    def test_missing_incident_on_telemetry_warns(self) -> None:
        result = RULE_REGISTRY["R-07"].handler(_event())
        assert result.result == "WARN"
        assert "missing" in result.detail

    def test_missing_incident_on_identity_passes_not_applicable(self) -> None:
        result = RULE_REGISTRY["R-07"].handler(Event(event_type="identity"))
        assert result.result == "PASS"
        assert "not applicable" in result.detail


class TestR08:
    """R-08: Physically impossible telemetry (TC-006-05)."""

    def test_tc_006_05_soc_jump_without_charging_hard_fail(self) -> None:
        fixture = load_fixture("event_impossible_soc.json")
        result = RULE_REGISTRY["R-08"].handler(Event.model_validate(fixture["event"]))
        assert result.rule_id == "R-08"
        assert result.result == "HARD_FAIL"

    def test_soc_jump_with_charging_source_passes(self) -> None:
        result = RULE_REGISTRY["R-08"].handler(
            _event(soc_percent=70.0, prior_soc_percent=60.0, charging_source_present=True)
        )
        assert result.result == "PASS"

    def test_small_soc_jump_passes(self) -> None:
        result = RULE_REGISTRY["R-08"].handler(
            _event(soc_percent=63.0, prior_soc_percent=60.0, charging_source_present=False)
        )
        assert result.result == "PASS"

    def test_small_soc_jump_unknown_charging_source_passes(self) -> None:
        result = RULE_REGISTRY["R-08"].handler(
            _event(soc_percent=63.0, prior_soc_percent=60.0, charging_source_present=None)
        )
        assert result.result == "PASS"

    def test_soc_jump_unknown_charging_source_hard_fail(self) -> None:
        result = RULE_REGISTRY["R-08"].handler(
            _event(soc_percent=70.0, prior_soc_percent=60.0, charging_source_present=None)
        )
        assert result.result == "HARD_FAIL"
        assert "unknown" in result.detail

    def test_missing_soc_on_telemetry_warns(self) -> None:
        result = RULE_REGISTRY["R-08"].handler(_event(prior_soc_percent=60.0))
        assert result.result == "WARN"
        assert "missing" in result.detail

    def test_missing_soc_on_identity_passes_not_applicable(self) -> None:
        result = RULE_REGISTRY["R-08"].handler(Event(event_type="identity", prior_soc_percent=60.0))
        assert result.result == "PASS"
        assert "not applicable" in result.detail

    def test_missing_prior_soc_passes_with_note(self) -> None:
        result = RULE_REGISTRY["R-08"].handler(_event(soc_percent=70.0))
        assert result.result == "PASS"
        assert result.detail == INSUFFICIENT_CONTEXT_DETAIL


class TestAllRulesPassFixture:
    """Every rule returns PASS for the TC-006-03 all-pass fixture event."""

    @pytest.mark.parametrize("rule_id", [f"R-{i:02d}" for i in range(1, 9)])
    def test_rule_passes_on_all_pass_fixture(self, rule_id: str) -> None:
        fixture = load_fixture("event_all_pass.json")
        result = RULE_REGISTRY[rule_id].handler(Event.model_validate(fixture["event"]))
        assert result.rule_id == rule_id
        assert result.result == "PASS"


class TestPurity:
    """Handlers are pure: they only read the event (Blueprint contract)."""

    def test_event_unchanged_after_evaluation(self) -> None:
        event = Event.model_validate(load_fixture("event_all_pass.json")["event"])
        snapshot = event.model_dump_json()
        for definition in RULE_REGISTRY.values():
            definition.handler(event)
        assert event.model_dump_json() == snapshot

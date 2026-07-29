"""Engine-level tests: multi-rule aggregation and gate decisions (PRD 12)."""

import logging
from datetime import datetime, timezone

import pytest

import sim_006.rules as rules
from sim_006.engine import RuleEngine, RuleSelectionError
from sim_006.models import EvaluationRequest, Event
from tests.conftest import load_fixture

FIXED_NOW = datetime(2026, 7, 29, 14, 30, 5, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _freeze_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Freeze the evaluation clock so R-01 staleness checks are deterministic."""
    monkeypatch.setattr(rules, "_utcnow", lambda: FIXED_NOW)


def _request(fixture_name: str) -> EvaluationRequest:
    """Build an EvaluationRequest from a fixture file.

    Args:
        fixture_name: Fixture file name in tests/fixtures/.

    Returns:
        The parsed EvaluationRequest.
    """
    return EvaluationRequest.model_validate(load_fixture(fixture_name))


class TestGateAggregation:
    """Worst-result-wins gate aggregation (PRD Section 6)."""

    def test_tc_006_03_all_pass(self) -> None:
        response = RuleEngine().evaluate(_request("event_all_pass.json"))
        assert response.rules_evaluated == 8
        assert {result.result for result in response.results} == {"PASS"}
        assert response.overall_gate == "PASS"
        assert response.gate_reason == "All 8 rules passed"
        assert response.simulated is True

    def test_tc_006_04_hard_fail_overrides_warn(self) -> None:
        response = RuleEngine().evaluate(_request("event_mixed_result.json"))
        results_by_id = {result.rule_id: result.result for result in response.results}
        assert results_by_id == {"R-02": "HARD_FAIL", "R-05": "WARN", "R-06": "PASS"}
        assert response.rules_evaluated == 3
        assert response.overall_gate == "HARD_FAIL"
        assert response.gate_reason == "Rule R-02 triggered HARD_FAIL"
        assert response.simulated is True

    def test_worst_warn_when_no_hard_fail(self) -> None:
        response = RuleEngine().evaluate(_request("event_voltage_warn.json"))
        assert response.overall_gate == "WARN"
        assert response.gate_reason == "Rule R-05 triggered WARN"

    def test_multiple_same_severity_triggers(self) -> None:
        event = Event.model_validate(
            {
                "event_type": "telemetry",
                "timestamp": None,
                "voltage_v": 100.0,
                "temperature_c": 25.0,
            }
        )
        request = EvaluationRequest(battery_id="BID-009", event=event, rule_ids=["R-02", "R-05"])
        response = RuleEngine().evaluate(request)
        assert response.overall_gate == "HARD_FAIL"
        assert response.gate_reason == "Rules R-02, R-05 triggered HARD_FAIL"

    def test_result_order_matches_request_order(self) -> None:
        response = RuleEngine().evaluate(_request("event_mixed_result.json"))
        assert [result.rule_id for result in response.results] == ["R-02", "R-05", "R-06"]


class TestRuleBypass:
    """Excluded rules do not count toward the gate, and the bypass is logged."""

    def test_bypassed_failing_rule_does_not_affect_gate(self) -> None:
        fixture = load_fixture("event_missing_timestamp.json")
        request = EvaluationRequest(
            battery_id=fixture["battery_id"],
            event=Event.model_validate(fixture["event"]),
            rule_ids=["R-05"],
        )
        response = RuleEngine().evaluate(request)
        assert response.overall_gate == "PASS"
        assert response.rules_evaluated == 1

    def test_bypass_is_logged_not_silent(self, caplog: pytest.LogCaptureFixture) -> None:
        fixture = load_fixture("event_missing_timestamp.json")
        request = EvaluationRequest(
            battery_id=fixture["battery_id"],
            event=Event.model_validate(fixture["event"]),
            rule_ids=["R-05"],
        )
        with caplog.at_level(logging.WARNING, logger="sim_006.engine"):
            response = RuleEngine().evaluate(request)
        assert "bypassed" in caplog.text
        assert "R-02" in caplog.text
        assert "did not count toward the gate decision" in caplog.text
        assert "bypassed" not in response.gate_reason

    def test_evaluating_all_rules_logs_no_bypass(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="sim_006.engine"):
            response = RuleEngine().evaluate(_request("event_all_pass.json"))
        assert "bypassed" not in caplog.text
        assert response.gate_reason == "All 8 rules passed"


class TestRuleSelectionErrors:
    """Invalid rule selections are rejected before evaluation (Build Spec 4)."""

    def test_unknown_rule_id_rejected(self) -> None:
        fixture = _request("event_all_pass.json").model_dump()
        fixture["rule_ids"] = ["R-99"]
        request = EvaluationRequest.model_validate(fixture)
        with pytest.raises(RuleSelectionError) as exc_info:
            RuleEngine().evaluate(request)
        assert exc_info.value.error == "unknown_rule_id"
        assert exc_info.value.payload == {
            "error": "unknown_rule_id",
            "detail": "Rule ID 'R-99' not found. Valid rule IDs: "
            "R-01, R-02, R-03, R-04, R-05, R-06, R-07, R-08",
            "simulated": True,
        }

    def test_empty_rule_list_rejected(self) -> None:
        fixture = _request("event_all_pass.json").model_dump()
        fixture["rule_ids"] = []
        request = EvaluationRequest.model_validate(fixture)
        with pytest.raises(RuleSelectionError) as exc_info:
            RuleEngine().evaluate(request)
        assert exc_info.value.error == "empty_rule_selection"
        assert exc_info.value.payload["simulated"] is True


class TestStatelessness:
    """The engine holds no state between calls (PRD Sections 7 and 13)."""

    def test_repeated_evaluation_is_deterministic(self) -> None:
        request = _request("event_all_pass.json")
        engine = RuleEngine()
        first = engine.evaluate(request)
        second = engine.evaluate(request)
        assert first.model_dump_json() == second.model_dump_json()

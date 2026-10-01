import pytest

from sim_006.engine import RuleEngine
from sim_006.simulator import SCENARIOS, generate_request


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_every_profile_is_valid_and_evaluable(scenario: str) -> None:
    response = RuleEngine().evaluate(generate_request(scenario))
    assert response.simulated is True
    assert response.rules_evaluated == 8


@pytest.mark.parametrize(
    ("scenario", "rule_id"),
    [
        ("replay", "R-01"), ("missing_timestamp", "R-02"),
        ("invalid_certificate", "R-03"), ("firmware_mismatch", "R-04"),
        ("unsafe_voltage", "R-05"), ("critical_temperature", "R-06"),
        ("cyber_incident", "R-07"), ("impossible_soc", "R-08"),
    ],
)
def test_profiles_trigger_their_named_rule(scenario: str, rule_id: str) -> None:
    response = RuleEngine().evaluate(generate_request(scenario))
    result = next(result for result in response.results if result.rule_id == rule_id)
    assert result.result == "HARD_FAIL"


def test_multi_condition_profile_aggregates_worst_result() -> None:
    response = RuleEngine().evaluate(generate_request("multi_condition"))
    assert response.overall_gate == "HARD_FAIL"
    assert {result.rule_id for result in response.results if result.result == "HARD_FAIL"} >= {
        "R-05", "R-06", "R-07"
    }
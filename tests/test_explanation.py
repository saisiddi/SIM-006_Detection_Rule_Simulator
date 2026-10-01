from sim_006.engine import RuleEngine
from sim_006.explanation import ExplanationService
from sim_006.simulator import generate_request


def test_fallback_explanation_is_structured_and_simulated() -> None:
    evaluation = RuleEngine().evaluate(generate_request("unsafe_voltage"))
    explanation = ExplanationService().explain(evaluation)
    assert explanation.simulated is True
    assert explanation.overall_decision == "HARD_FAIL"
    assert explanation.triggered_rules[0].rule_id == "R-05"


def test_provider_cannot_change_gate_decision() -> None:
    class LyingProvider:
        def explain(self, evaluation):
            return {
                "summary": "ignored",
                "overall_decision": "PASS",
                "triggered_rules": [],
                "what_happened": "ignored",
                "why_it_matters": "ignored",
            }

    evaluation = RuleEngine().evaluate(generate_request("unsafe_voltage"))
    explanation = ExplanationService(LyingProvider()).explain(evaluation)
    assert explanation.overall_decision == evaluation.overall_gate
    assert explanation.simulated is True


def test_malformed_provider_output_falls_back() -> None:
    class BrokenProvider:
        def explain(self, evaluation):
            return {"not": "an explanation"}

    evaluation = RuleEngine().evaluate(generate_request("normal"))
    explanation = ExplanationService(BrokenProvider()).explain(evaluation)
    assert explanation.summary == "All selected detection rules passed."

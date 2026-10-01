"""Safe, structured explanations for deterministic evaluation responses."""

from collections.abc import Mapping
from typing import Protocol

from pydantic import BaseModel, Field, ValidationError

from sim_006.models import EvaluationResponse


class TriggeredRuleExplanation(BaseModel):
    rule_id: str
    rule_name: str
    severity: str
    explanation: str


class ExplanationResponse(BaseModel):
    simulated: bool = True
    ai_generated: bool = False
    summary: str
    overall_decision: str
    triggered_rules: list[TriggeredRuleExplanation] = Field(default_factory=list)
    what_happened: str
    why_it_matters: str
    recommended_checks: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ExplanationProvider(Protocol):
    def explain(self, evaluation: EvaluationResponse) -> Mapping[str, object]: ...


class DeterministicExplanationProvider:
    """Fallback provider that explains results without an external model."""

    def explain(self, evaluation: EvaluationResponse) -> Mapping[str, object]:
        triggered = [result for result in evaluation.results if result.result != "PASS"]
        if triggered:
            summary = f"The simulator produced an overall {evaluation.overall_gate} decision."
            what_happened = " ".join(f"{result.rule_id}: {result.detail}." for result in triggered)
            checks = [f"Review the condition reported by {result.rule_id}." for result in triggered]
        else:
            summary = "All selected detection rules passed."
            what_happened = "No selected rule reported a warning or hard failure."
            checks = ["Continue monitoring subsequent simulated events."]
        return {
            "simulated": True,
            "ai_generated": False,
            "summary": summary,
            "overall_decision": evaluation.overall_gate,
            "triggered_rules": [
                {
                    "rule_id": result.rule_id,
                    "rule_name": result.rule_name,
                    "severity": result.result,
                    "explanation": result.detail,
                }
                for result in triggered
            ],
            "what_happened": what_happened,
            "why_it_matters": (
                "The overall decision is determined by the deterministic rule engine."
            ),
            "recommended_checks": checks,
            "limitations": [
                "This is a simulated explanation, not an operational incident response.",
                "AI does not determine or modify rule results.",
            ],
        }


class ExplanationService:
    """Adapt optional provider output while keeping the engine authoritative."""

    def __init__(self, provider: ExplanationProvider | None = None) -> None:
        self.provider = provider

    def explain(self, evaluation: EvaluationResponse) -> ExplanationResponse:
        provider = self.provider or DeterministicExplanationProvider()
        try:
            parsed = ExplanationResponse.model_validate(provider.explain(evaluation))
        except (ValidationError, TypeError, ValueError):
            parsed = ExplanationResponse.model_validate(
                DeterministicExplanationProvider().explain(evaluation)
            )
        parsed.overall_decision = evaluation.overall_gate
        parsed.simulated = True
        return parsed


def configured_explanation_service() -> ExplanationService:
    """Return the local fallback until an explicitly configured provider exists."""
    return ExplanationService()

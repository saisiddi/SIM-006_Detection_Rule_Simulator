"""SIM-006 Detection Rule Simulator module.

Exports the Pydantic data models, rule registry, and rule engine used by all
three interfaces (CLI, FastAPI, Streamlit).
"""

from sim_006.engine import RuleEngine, RuleSelectionError
from sim_006.explanation import ExplanationResponse, ExplanationService
from sim_006.models import (
    EvaluationRequest,
    EvaluationResponse,
    Event,
    ExplanationRequest,
    RuleEvaluationResult,
)
from sim_006.rules import RULE_REGISTRY
from sim_006.simulator import generate_event, generate_request

__all__ = [
    "Event",
    "EvaluationRequest",
    "EvaluationResponse",
    "ExplanationRequest",
    "ExplanationResponse",
    "ExplanationService",
    "RuleEvaluationResult",
    "RuleEngine",
    "RuleSelectionError",
    "RULE_REGISTRY",
    "generate_event",
    "generate_request",
]

"""SIM-006 Detection Rule Simulator module.

Exports the Pydantic data models, rule registry, and rule engine used by all
three interfaces (CLI, FastAPI, Streamlit).
"""

from sim_006.engine import RuleEngine, RuleSelectionError
from sim_006.models import (
    EvaluationRequest,
    EvaluationResponse,
    Event,
    RuleEvaluationResult,
)
from sim_006.rules import RULE_REGISTRY

__all__ = [
    "Event",
    "EvaluationRequest",
    "EvaluationResponse",
    "RuleEvaluationResult",
    "RuleEngine",
    "RuleSelectionError",
    "RULE_REGISTRY",
]

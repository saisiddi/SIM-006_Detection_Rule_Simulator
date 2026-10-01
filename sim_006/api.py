"""FastAPI application for SIM-006 (PRD Section 10.2).

Exposes POST /evaluate, GET /rules, and GET /health, all delegating to the
same RuleEngine used by the CLI and Streamlit UI. Rule-selection errors map
to HTTP 400 with the Build Spec Section 4 payload; malformed payloads get
FastAPI's default HTTP 422 (intentionally not overridden).
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from sim_006.engine import RuleEngine, RuleSelectionError
from sim_006.explanation import ExplanationResponse, configured_explanation_service
from sim_006.models import EvaluationRequest, EvaluationResponse, ExplanationRequest
from sim_006.rules import RULE_REGISTRY

logger = logging.getLogger(__name__)

app = FastAPI(
    title="SIM-006 Detection Rule Simulator",
    description="Simulated detection rule evaluation. All output is simulated.",
    version="0.1.0",
)


@app.exception_handler(RuleSelectionError)
async def rule_selection_error_handler(request: Request, exc: RuleSelectionError) -> JSONResponse:
    """Map rule-selection errors to HTTP 400 (Build Spec Section 4).

    Args:
        request: The incoming request (unused, required by FastAPI).
        exc: The raised RuleSelectionError.

    Returns:
        HTTP 400 response carrying the error payload tagged simulated=True.
    """
    return JSONResponse(status_code=400, content=exc.payload)


@app.post("/evaluate", response_model=EvaluationResponse)
def evaluate(request: EvaluationRequest) -> EvaluationResponse:
    """Evaluate one or more detection rules against an event.

    Args:
        request: The evaluation request (battery_id, event, rule IDs or "all").

    Returns:
        The evaluation response with per-rule results and the overall gate.
    """
    return RuleEngine().evaluate(request)


@app.post("/explain", response_model=ExplanationResponse)
def explain(request: ExplanationRequest) -> ExplanationResponse:
    """Explain an existing deterministic response without re-evaluating it."""
    return configured_explanation_service().explain(request.evaluation)


@app.get("/rules")
def list_rules() -> dict[str, object]:
    """List all 8 detection rules with descriptions and thresholds.

    Returns:
        The rule catalogue tagged simulated=True.
    """
    rules = [
        {
            "rule_id": definition.rule_id,
            "rule_name": definition.rule_name,
            "description": definition.description,
        }
        for definition in RULE_REGISTRY.values()
    ]
    return {"rules": rules, "simulated": True}


@app.get("/health")
def health() -> dict[str, object]:
    """Health check endpoint.

    Returns:
        Status payload confirming the API is running, tagged simulated=True.
    """
    return {"status": "ok", "simulated": True}
